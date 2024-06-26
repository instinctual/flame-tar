# DirectoryTools for Flame v1.0
# Original Copyright (c) 2019 Bob Maple (bobm-matchbox [at] idolum.com)
# Modified by Gary Oberbrunner, garyo@darkstarsystems.com, for Instinctual
#
# For Flame 2020 and above - place in /opt/Autodesk/shared/python/
#
# Adds a submenu to the MediaHub context menu in Files mode to tar and zip
# a selected directory or directories (makes separate files for each)
#
# Select a directory in the browser and right-click to access
#
# Uses Backburner to run tar commands


import os, subprocess, time, tempfile, shlex
import logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger('DirectoryTools.tar')

config = dict(
  BBMANAGER="manager",
  BBGROUP="TARNODES",
  PRIORITY="30",
  CMDJOB="/opt/Autodesk/backburner/cmdjob"
)

def ask_yesno(dlg_msg, dlg_title):
  """Prompt user for yes/cancel using Qt widgets"""
  try:
    from PySide6.QtWidgets import QMessageBox
    usingPyside6 = True
  except ImportError:
    from PySide2.QtWidgets import QMessageBox
    usingPyside6 = False

  qtMsgBox = QMessageBox()
  qtMsgBox.setWindowTitle( dlg_title )
  qtMsgBox.setText( dlg_msg )
  qtMsgBox.setStandardButtons( QMessageBox.Yes | QMessageBox.Cancel )
  qtMsgBox.setDefaultButton( QMessageBox.Yes )
  if usingPyside6:
    res = qtMsgBox.exec()
  else:
    res = qtMsgBox.exec_()

  if res == QMessageBox.Cancel :
    return( False )
  else:
    return( True )


##### Main Flame hook handler
#####

def get_mediahub_files_custom_ui_actions():

  def menu_enabled(sel):
    logger.debug('menu_enabled(%s)...', [x.path for x in sel])
    is_enabled = False
    for item in sel:
      if os.path.isdir(item.path):
        is_enabled = True
    logger.info('menu_enabled(%s) = %s', [x.path for x in sel], is_enabled)
    return is_enabled

  def rreplace(s, old, new, count):
    """Replace in s the rightmost 'count' occurrences of old with new"""
    return new.join(s.rsplit(old, count))

  def get_dest_path(srcpath):
    destpath = srcpath
    found = destpath.rfind('_xyz/')
    if found >= 0:
      destpath = rreplace(destpath, '_xyz/', '_dcdm/', 1)
    return destpath

  def tardir_go(sel, prompt=ask_yesno, test_mode=False) :
    try:
      logger.info('tardir_go(%s, test_mode=%s)', [x.path for x in sel], test_mode)
      plural = "s" if len(sel) > 1 else ""
      if not prompt('{} folder{} selected for TAR; OK?'.format(len(sel), plural),
                    'tarring {} folder{}'.format(len(sel), plural)):
        return

      returncodes = []
      for curitem in sel:
        if not os.path.isdir(curitem.path):
          continue
        path = curitem.path.rstrip('/') # remove trailing slashes
        archive_path = path + '.tar'
        if os.path.isfile(archive_path) and \
           not prompt( "Overwrite " + archive_path + " ?", archive_path + " exists" ):
          continue

        destpath = get_dest_path(path)

        # Run on Backburner using cmdjob
        vars = config.copy()
        vars['TARNAME'] = destpath
        vars['BASENAME'] = os.path.basename(path)
        vars['JOBNAME'] = os.path.basename(path) + ' DCDM'
        vars['PARENTDIR'] = os.path.dirname(path)

        cmdline = ['{CMDJOB}',
                   '-manager:{BBMANAGER}',
                   '-group:{BBGROUP}',
                   '-priority:{PRIORITY}',
                   '-jobName', '{JOBNAME}',
                   '-userRights',
                   '-description', 'TAR + List file',
                   'sh', '-c',
                   '/usr/bin/tar -cf {TARNAME}.tar -C {PARENTDIR} {BASENAME} ; '
                   ' tar -tvf {TARNAME}.tar | sort > {TARNAME}.tar.list']
        cmdline = [x.format(**vars) for x in cmdline]

        if test_mode:
          return cmdline

        # Run job
        cmd = subprocess.Popen(cmdline)
        rc = cmd.wait()
        logger.info('tardir_go("%s") returns status %s', path, rc)
        returncodes.append(rc)
      return returncodes
    except Exception as e:
      logger.exception('tardir_go: got exception %s', e)
      raise

  return [
    {
      "name": "Directory Tools",
      "actions": [
        {
          "name": "TAR Directory",
          "isEnabled": menu_enabled,
          "execute": tardir_go
        },
      ]
    }
  ]

# Use pytest to run this test
def test_tar(monkeypatch):
  """Test the tar action -- check resulting cmd line and try a dummy run"""
  class PathItem:
      def __init__(self, path):
        self.path = path

  def fake_askyesno(msg, title):
    return True

  for d in ('/tmp/foo', '/tmp/foo/bar',
            '/tmp/foo_xyz', '/tmp/foo_xyz/sub', '/tmp/foo_xyz/sub/sub2',
            '/tmp/foo_dcdm'):
    try:
      os.mkdir(d)
    except OSError:
      pass

  actions = get_mediahub_files_custom_ui_actions()
  sel = [PathItem('/tmp/foo')]
  tardir_go = actions[0]['actions'][0]['execute']
  is_enabled = actions[0]['actions'][0]['isEnabled']

  # test is_enabled
  status = is_enabled(sel)
  assert status == True

  cmdline = tardir_go(sel, fake_askyesno, True)
  assert cmdline[0] == config['CMDJOB']
  assert cmdline[11] == '/usr/bin/tar -cf /tmp/foo.tar -C /tmp foo ;  tar -tvf /tmp/foo.tar | sort > /tmp/foo.tar.list'

  # Same, with trailing slash
  sel = [PathItem('/tmp/foo/')]
  cmdline = tardir_go(sel, fake_askyesno, True)
  assert cmdline[0] == config['CMDJOB']
  assert cmdline[11] == '/usr/bin/tar -cf /tmp/foo.tar -C /tmp foo ;  tar -tvf /tmp/foo.tar | sort > /tmp/foo.tar.list'

  # Try with a _xyz path, should get substituted
  sel = [PathItem('/tmp/foo_xyz/sub')]
  cmdline = tardir_go(sel, fake_askyesno, True)
  assert cmdline[0] == config['CMDJOB']
  assert cmdline[11] == '/usr/bin/tar -cf /tmp/foo_dcdm/sub.tar -C /tmp/foo_xyz sub ;  tar -tvf /tmp/foo_dcdm/sub.tar | sort > /tmp/foo_dcdm/sub.tar.list'

  # Try another _xyz path, deeper
  sel = [PathItem('/tmp/foo_xyz/sub/sub2')]
  cmdline = tardir_go(sel, fake_askyesno, True)
  assert cmdline[0] == config['CMDJOB']
  assert cmdline[11] == '/usr/bin/tar -cf /tmp/foo_dcdm/sub/sub2.tar -C /tmp/foo_xyz/sub sub2 ;  tar -tvf /tmp/foo_dcdm/sub/sub2.tar | sort > /tmp/foo_dcdm/sub/sub2.tar.list'


  # Now actually try it
  rc = tardir_go(sel, fake_askyesno, False)
  assert rc[0] in (0, 6)           # 0 = success, 6 = connection refused

  sel = [PathItem('/tmp/foo'), PathItem('/tmp/foo')]
  # Try it with two paths selected
  rc = tardir_go(sel, fake_askyesno, False)
  assert len(rc) == 2
  assert rc[0] in (0, 6)
  assert rc[1] in (0, 6)


  # Clean up
  for d in ('/tmp/foo/bar', '/tmp/foo'):
    try:
      os.rmdir(d)
    except OSError:
      pass
