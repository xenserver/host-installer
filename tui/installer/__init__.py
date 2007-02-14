import tui.installer.screens 
import tui.progress
import uicontroller
import hardware
import netutil
import repository

from snack import *

def runMainSequence(results, ram_warning, vt_warning, installed_products):
    """ Runs the main installer sequence and updtes results with a
    set of values ready for the backend. """
    uis = tui.installer.screens
    Step = uicontroller.Step

    seq = [
        Step(uis.welcome_screen),
        Step(uis.eula_screen),
        Step(uis.hardware_warnings,
             args=[ram_warning, vt_warning],
             predicate=lambda _:(ram_warning or vt_warning)),
        Step(uis.get_installation_type, args=[installed_products]),
        Step(uis.backup_existing_installation),
        Step(uis.select_primary_disk),
        Step(uis.select_guest_disks),
        Step(uis.confirm_erase_volume_groups),
        Step(uis.select_installation_source),
        Step(uis.setup_runtime_networking),
        Step(uis.get_source_location),
        Step(uis.verify_source),
        Step(uis.get_root_password),
        Step(uis.get_timezone_region),
        Step(uis.get_timezone_city),
        Step(uis.get_time_configuration_method),
        Step(uis.get_ntp_servers),
        Step(uis.determine_basic_network_config),
        Step(uis.get_name_service_configuration),
        Step(uis.confirm_installation),
        ]
    return uicontroller.runSequence(seq, results)

def more_media_sequence(installed_repo_ids):
    """ Displays the sequence of screens required to load additional
    media to install from.  installed_repo_ids is a list of repository
    IDs of repositories we already installed from, to help avoid
    issues where multiple CD drives are present."""
    def get_more_media(_):
        """ 'Please insert disk' dialog. """
        done = False
        while not done:
            more = tui.progress.OKDialog("New Media", "Please insert your extra disc now.", True)
            if more == "cancel":
                # they hit cancel:
                rv = -1
                done = True
            else:
                # they hit OK - check there is a disc
                repos = repository.repositoriesFromDefinition('local', '')
                if len(repos) == 0:
                    ButtonChoiceWindow(
                        tui.screen, "Error",
                        "No installation files were found - please check your disc and try again.",
                        ['Back'])
                else:
                    # found repositories - can leave this screen
                    rv = 1
                    done = True
        return rv

    def confirm_more_media(_):
        """ 'Really use this disc?' screen. """
        repos = repository.repositoriesFromDefinition('local', '')
        assert len(repos) > 0

        media_contents = []
        for r in repos:
            if r.identifier() in installed_repo_ids:
                media_contents.append(" * %s (already installed)" % r.name())
            else:
                media_contents.append(" * %s" % r.name())
        text = "The media you have inserted contains:\n\n" + "\n".join(media_contents)

        done = False
        while not done:
            ans = ButtonChoiceWindow(tui.screen, "New Media", text, ['Use media', 'Verify media', 'Back'], width=50)
            
            if ans == 'verify media':
                if tui.installer.screens.interactive_source_verification('local', ''):
                    tui.progress.OKDialog("Media Check", "No problems were found with your media.")
            elif ans == 'back':
                rc = -1
                done = True
            else:
                rc = 1
                done = True

        return rc

    seq = [ Step(get_more_media), Step(confirm_more_media) ]
    direction = uicontroller.runSequence(seq, {})
    return direction == 1
