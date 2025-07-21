# SPDX-License-Identifier: GPL-2.0-only

from snack import *
import constants
import version
import product
import tui
import tui.progress
from uicontroller import SKIP_SCREEN, LEFT_BACKWARDS, RIGHT_FORWARDS, REPEAT_STEP
import repository
import generalui
import urllib.parse
import util
from xcp import logger

def selectDefault(key, entries):
    """ Given a list of (text, key) and a key to select, returns the appropriate
    text,key pair, or None if not in entries. """

    for text, k in entries:
        if key == k:
            return text, k
    return None

(
    REPOCHK_NO_ACCESS,
    REPOCHK_NO_REPO,
    REPOCHK_NO_BASE_REPO,
    REPOCHK_PLATFORM_VERSION_MISMATCH,
    REPOCHK_NO_ERRORS
) = list(range(5))

def check_repo_def(definition, require_base_repo):
    """ Check that the repository source definition gives access to suitable
    repositories. """
    try:
        tui.progress.showMessageDialog("Please wait", "Searching for repository...")
        repos = repository.repositoriesFromDefinition(*definition)
        tui.progress.clearModelessDialog()
    except Exception as e:
        logger.log("Exception trying to access repository: %s" % e)
        logger.logException(e)
        tui.progress.clearModelessDialog()
        return REPOCHK_NO_ACCESS
    else:
        if len(repos) == 0:
            return REPOCHK_NO_REPO
        elif constants.MAIN_REPOSITORY_NAME not in [r.identifier() for r in repos] and require_base_repo:
            return REPOCHK_NO_BASE_REPO

    return REPOCHK_NO_ERRORS

def interactive_check_repo_def(definition, require_base_repo):
    """ Check repo definition and display an appropriate dialog based
    on outcome.  Returns boolean indicating whether to continue with
    the definition given or not. """

    rc = check_repo_def(definition, require_base_repo)
    if rc == REPOCHK_NO_ACCESS:
        ButtonChoiceWindow(
            tui.screen,
            "Problem With Location",
            "Setup was unable to access the location you specified - please check and try again.",
            ['Ok']
            )
    elif rc in [REPOCHK_NO_REPO, REPOCHK_NO_BASE_REPO]:
        ButtonChoiceWindow(
           tui.screen,
           "Problem With Location",
           "A base installation repository was not found at that location.  Please check and try again.",
           ['Ok']
           )
    elif rc == REPOCHK_PLATFORM_VERSION_MISMATCH:
        cont = ButtonChoiceWindow(
            tui.screen,
            "Version Mismatch",
            "The location you specified contains packages designed for a different version of %s.\n\nThis may result in failures during installation, or an incorrect installation of the product." % (version.PRODUCT_BRAND or version.PLATFORM_NAME),
            ['Continue anyway', 'Back']
            )
        return cont in ['continue anyway', None]
    else:
        return True

def select_repo_source(answers, title, text, require_base_repo=True):
    ENTRY_LOCAL = 'Local media', 'local'
    ENTRY_URL = 'HTTP or FTP', 'url'
    ENTRY_NFS = 'NFS', 'nfs'
    entries = [ ENTRY_LOCAL ]

    default = ENTRY_LOCAL
    if len(answers['network-hardware'].keys()) > 0:
        entries += [ ENTRY_URL, ENTRY_NFS ]

        # default selection?
        if 'source-media' in answers:
            default = selectDefault(answers['source-media'], entries)

    (button, entry) = ListboxChoiceWindow(
        tui.screen,
        title,
        text,
        entries,
        ['Ok', 'Back'], default=default, help='selreposrc'
        )

    if button == 'back': return LEFT_BACKWARDS

    # clear the source-address key?
    if 'source-media' in answers and answers['source-media'] != entry:
        answers['source-address'] = ""

    # store their answer:
    answers['source-media'] = entry

    # if local, check that the media is correct:
    if entry == 'local':
        answers['source-address'] = ""
        if require_base_repo and not interactive_check_repo_def(('local', ''), True):
            return REPEAT_STEP

    return RIGHT_FORWARDS

def get_url_location(answers, require_base_repo):
    text = "Please enter the URL for your HTTP or FTP repository and, optionally, a username and password"
    url_field = Entry(50)
    user_field = Entry(16)
    passwd_field = Entry(16, password=1)
    url_text = Textbox(11, 1, "URL:")
    user_text = Textbox(11, 1, "Username:")
    passwd_text = Textbox(11, 1, "Password:")

    if 'source-address' in answers and answers['source-address'] != '':
        url_field.set(answers['source-address'].getPlainURL())
        if answers['source-address'].getUsername() is not None:
            user_field.set(answers['source-address'].getUsername())
        if answers['source-address'].getPassword() is not None:
            passwd_field.set(answers['source-address'].getPassword())

    done = False
    while not done:
        gf = GridFormHelp(tui.screen, "Specify Repository", 'geturlloc', 1, 3)
        bb = ButtonBar(tui.screen, [ 'Ok', 'Back' ])
        t = TextboxReflowed(50, text)

        entry_grid = Grid(2, 3)
        entry_grid.setField(url_text, 0, 0)
        entry_grid.setField(url_field, 1, 0)
        entry_grid.setField(user_text, 0, 1)
        entry_grid.setField(user_field, 1, 1, anchorLeft=1)
        entry_grid.setField(passwd_text, 0, 2)
        entry_grid.setField(passwd_field, 1, 2, anchorLeft=1)

        gf.add(t, 0, 0, padding=(0, 0, 0, 1))
        gf.add(entry_grid, 0, 1, padding=(0, 0, 0, 1))
        gf.add(bb, 0, 2, growx=1)

        button = bb.buttonPressed(gf.runOnce())

        if button == 'back': return LEFT_BACKWARDS

        if user_field.value() != '':
            quoted_user = urllib.parse.quote(user_field.value(), safe='')
            if passwd_field.value() != '':
                quoted_passwd = urllib.parse.quote(passwd_field.value(), safe='')
                urlstr = url_field.value().replace('//', '//%s:%s@' % (quoted_user, quoted_passwd), 1)
            else:
                urlstr = url_field.value().replace('//', '//%s@' % quoted_user, 1)
        else:
            urlstr = url_field.value()
        if len(urlstr) > 0:
            answers['source-address'] = util.URL(urlstr)
            done = interactive_check_repo_def((answers['source-media'], answers['source-address']), require_base_repo)

    return RIGHT_FORWARDS

def get_nfs_location(answers, require_base_rep):
    text = "Please enter the server and path of your NFS share (e.g. myserver:/my/directory)"
    label = "NFS Path:"

    done = False
    while not done:
        if 'source-address' in answers:
            default = answers['source-address']
        else:
            default = ""
        (button, result) = EntryWindow(
            tui.screen,
            "Specify Repository",
            text,
            [(label, default)], entryWidth=50, width=50,
            buttons=['Ok', 'Back'], help='getnfsloc')

        answers['source-address'] = result[0]

        if button == 'back': return LEFT_BACKWARDS

        done = interactive_check_repo_def((answers['source-media'], answers['source-address']), require_base_rep)

    return RIGHT_FORWARDS

def get_source_location(answers, require_base_rep):
    if answers['source-media'] == 'url':
        return get_url_location(answers, require_base_rep)
    else:
        return get_nfs_location(answers, require_base_rep)

# verify the installation source?
def verify_source(answers, label, require_base_repo):
    cap_label = ' '.join([a.capitalize() for a in label.split()])
    if 'source-media' in answers and 'source-address' in answers:
        media = answers['source-media']
        address = answers['source-address']
    else:
        media = 'local'
        address = ''
    done = False
    SKIP, VERIFY = list(range(2))
    entries = [ ("Skip verification", SKIP),
                ("Verify %s source" % label, VERIFY), ]

    if media == 'local':
        text = "Would you like to test your media?"
        default = selectDefault(VERIFY, entries)
    else:
        text = "Would you like to test your %s repository?  This may cause significant network traffic." % label
        default = selectDefault(SKIP, entries)

    while not done:
        (button, entry) = ListboxChoiceWindow(
            tui.screen, "Verify %s Source" % cap_label, text,
            entries, ['Ok', 'Back'], default=default, help='vfyrepo')

        if button == 'back': return LEFT_BACKWARDS

        if entry == VERIFY:
            # we need to do the verification:
            try:
                tui.progress.showMessageDialog("Please wait", "Searching for repository...")
                repos = repository.repositoriesFromDefinition(media, address)
                tui.progress.clearModelessDialog()

                if require_base_repo and constants.MAIN_REPOSITORY_NAME not in [r.identifier() for r in repos]:
                    ButtonChoiceWindow(
                        tui.screen, "Error",
                        """A base installation repository was not found.  Please check the address was valid and/or that the media was inserted correctly, and try again.""",
                        ['Ok'])
                else:
                    done = interactive_source_verification(repos, label)
            except Exception as e:
                logger.logException(e)
                ButtonChoiceWindow(
                    tui.screen, "Error",
                    """Unable to access location specified.  Please check the address was valid and/or that the media was inserted correctly, and try again.""",
                    ['Ok'])
        else:
            done = True

    return RIGHT_FORWARDS

def interactive_source_verification(repos, label):
    cap_label = ' '.join([a.capitalize() for a in label.split()])
    errors = []
    pd = tui.progress.initProgressDialog(
        "Verifying %s Source" % cap_label, "Initializing...",
        len(repos) * 100
        )
    tui.progress.displayProgressDialog(0, pd)
    for i in range(len(repos)):
        r = repos[i]
        def progress(x):
            #print i * 100 + x
            tui.progress.displayProgressDialog(i*100 + x, pd, "Checking %s..." % r.name())
        errors.extend(r.check(progress))

    tui.progress.clearModelessDialog()

    if len(errors) != 0:
        errtxt = generalui.makeHumanList([x.name for x in errors])
        ButtonChoiceWindow(
            tui.screen,
            "Problems Found",
            "Some packages appeared damaged.  These were: %s" % errtxt,
            ['Ok']
            )
        return False
    else:
        repo_names = generalui.makeHumanList( ['"%s"' %x.name() for x in repos])
        ButtonChoiceWindow(
            tui.screen,
            "Verification Successful",
            "Verification of your %s(s) %s completed successfully: no problems were found." % (label, repo_names),
            ['Ok']
            )
    return True
