# Copyright (c) 2005-2006 XenSource, Inc. All use and distribution of this 
# copyrighted material is governed by and subject to terms and conditions 
# as licensed by XenSource, Inc. All other rights reserved.
# Xen, XenSource and XenEnterprise are either registered trademarks or 
# trademarks of XenSource Inc. in the United States and/or other countries.

###
# XEN CLEAN INSTALLER
# Installer TUI sequence definitions
#
# written by Andrew Peace

import tui.installer.screens 
import tui.progress
import tui.repo
import uicontroller
from uicontroller import SKIP_SCREEN, EXIT, LEFT_BACKWARDS, RIGHT_FORWARDS, REPEAT_STEP
import hardware
import netutil
import repository
import constants
import upgrade
import product
import snackutil
import diskutil
import version

from snack import *

def runMainSequence(results, ram_warning, vt_warning, suppress_extra_cd_dialog):
    """ Runs the main installer sequence and updates results with a
    set of values ready for the backend. """
    uis = tui.installer.screens
    Step = uicontroller.Step

    def upgrade_but_no_settings_predicate(answers):
        return answers['install-type'] == constants.INSTALL_TYPE_REINSTALL and \
            (not answers.has_key('installation-to-overwrite') or \
                 not answers['installation-to-overwrite'].settingsAvailable())

    netifs = netutil.getNetifList()
    has_multiple_nics = lambda _: len(netifs) > 1
    if len(netifs) == 1:
        results['net-admin-interface'] = netifs[0]

    is_reinstall_fn = lambda a: a['install-type'] == constants.INSTALL_TYPE_REINSTALL
    is_clean_install_fn = lambda a: a['install-type'] == constants.INSTALL_TYPE_FRESH
    is_using_remote_media_fn = lambda a: a['source-media'] in ['url', 'nfs']

    def requires_backup(answers):
        return answers.has_key("installation-to-overwrite") and \
               upgrade.getUpgrader(answers['installation-to-overwrite']).requires_backup

    def optional_backup(answers):
        return answers.has_key("installation-to-overwrite") and \
               upgrade.getUpgrader(answers['installation-to-overwrite']).optional_backup

#    def requires_repartition(answers):
#        return answers.has_key("installation-to-overwrite") and \
#               upgrade.getUpgrader(answers['installation-to-overwrite']).repartition

    def requires_target(answers):
        return answers['install-type'] == constants.INSTALL_TYPE_FRESH or \
               answers.has_key("installation-to-overwrite") and \
               upgrade.getUpgrader(answers['installation-to-overwrite']).prompt_for_target

    def preserve_settings(answers):
        return answers.has_key('preserve-settings') and \
               answers['preserve-settings']
    not_preserve_settings = lambda a: not preserve_settings(a)

    def local_media_predicate(answers):
        return answers.has_key('source-media') and \
               answers['source-media'] == 'local' and not suppress_extra_cd_dialog

    def iscsi_disks_enabled(answers):
        return answers.has_key('enable-iscsi') and answers['enable-iscsi'] == True

    def iscsi_primary_disk(answers):
        return diskutil.is_iscsi(answers['primary-disk'])

    def preserve_timezone(answers):
        if not_preserve_settings(answers):
            return False
        if not answers.has_key('installation-to-overwrite'):
            return False
        settings = answers['installation-to-overwrite'].readSettings()
        return settings.has_key('timezone') and not settings.has_key('request-timezone')
    not_preserve_timezone = lambda a: not preserve_timezone(a)

    def ha_enabled(answers):
        settings = {}
        if answers.has_key('installation-to-overwrite'):
            settings = answers['installation-to-overwrite'].readSettings()
        return settings.has_key('ha-armed') and settings['ha-armed']

    # initialise the list of installed/upgradeable products.
    # This may change if we later add an iscsi disk
    tui.progress.showMessageDialog("Please wait", "Checking for existing products...")
    results['installed-products'] = product.find_installed_products()
    results['upgradeable-products'] = upgrade.filter_for_upgradeable_products(results['installed-products'])
    tui.progress.clearModelessDialog()

    if not results.has_key('install-type'):
        results['install-type'] = constants.INSTALL_TYPE_FRESH
        results['preserve-settings'] = False

    seq = [
        Step(uis.welcome_screen),
        Step(uis.eula_screen),
        Step(uis.hardware_warnings,
             args=[ram_warning, vt_warning],
             predicates=[lambda _:(ram_warning or vt_warning)]),
        Step(uis.add_iscsi_disks,
             predicates=[iscsi_disks_enabled]),
        Step(uis.overwrite_warning,
             predicates=[lambda _:len(results['installed-products']) > 0 and len(results['upgradeable-products']) == 0]),
        Step(uis.get_installation_type, 
             predicates=[lambda _:len(results['upgradeable-products']) > 0]),
        Step(uis.upgrade_settings_warning,
             predicates=[upgrade_but_no_settings_predicate]),
        Step(uis.ha_master_upgrade,
             predicates=[is_reinstall_fn, ha_enabled]),
        Step(uis.remind_driver_repos,
             predicates=[is_reinstall_fn, preserve_settings]),
        Step(uis.backup_existing_installation,
             predicates=[is_reinstall_fn, optional_backup]),
        Step(uis.force_backup_screen,
             predicates=[is_reinstall_fn, requires_backup]),
#        Step(uis.repartition_existing,
#             predicates=[is_reinstall_fn, requires_repartition]),
        Step(uis.select_primary_disk,
             predicates=[requires_target]),
        Step(uis.select_guest_disks,
             predicates=[is_clean_install_fn]),
        Step(uis.confirm_erase_volume_groups,
             predicates=[is_clean_install_fn]),
        Step(tui.repo.select_repo_source, args = ["Select Installation Source", "Please select the type of source you would like to use for this installation"]),
        Step(uis.use_extra_media, args=[vt_warning],
             predicates=[local_media_predicate]),
        Step(uis.setup_runtime_networking, 
             predicates=[is_using_remote_media_fn]),
        Step(uis.get_source_location,
             predicates=[is_using_remote_media_fn]),
        Step(tui.repo.verify_source, args=['installation']),
        Step(uis.get_root_password,
             predicates=[not_preserve_settings]),
        Step(uis.get_iscsi_interface,
             predicates=[iscsi_primary_disk]),
        Step(uis.get_iscsi_interface_configuration,
             predicates=[iscsi_primary_disk]),
        Step(uis.get_admin_interface,
             predicates=[has_multiple_nics, not_preserve_settings]),
        Step(uis.get_admin_interface_configuration,
             predicates=[not_preserve_settings]),
        Step(uis.get_name_service_configuration,
             predicates=[not_preserve_settings]),
        Step(uis.get_timezone_region,
             predicates=[not_preserve_timezone]),
        Step(uis.get_timezone_city,
             predicates=[not_preserve_timezone]),
        Step(uis.get_time_configuration_method,
             predicates=[not_preserve_settings]),
        Step(uis.get_ntp_servers,
             predicates=[not_preserve_settings]),
        Step(uis.confirm_installation),
        ]
    return uicontroller.runSequence(seq, results)

def more_media_sequence(installed_repos):
    """ Displays the sequence of screens required to load additional
    media to install from.  installed_repos is a dictionary of repository
    IDs of repositories we already installed from, to help avoid
    issues where multiple CD drives are present.

    Returns pair: (install more, then ask again)"""
    def get_more_media(_):
        """ 'Please insert disk' dialog. """
        done = False
        while not done:
            more = tui.progress.OKDialog("New Media", "Please insert your Supplemental Pack now.", True)
            if more == "cancel":
                # they hit cancel:
                rv = EXIT
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
                    rv = RIGHT_FORWARDS
                    done = True
        return rv

    def check_requires(_):
        """ Check prerequisites and report if any are missing. """
        missing_repos = []
        main_repo_missing = False
        repos = repository.repositoriesFromDefinition('local', '')
        for r in repos:
            missing_repos += r.check_requires(installed_repos)

        if len(missing_repos) == 0:
            return SKIP_SCREEN

        text2 = ''
        for r in missing_repos:
            if r.startswith(constants.MAIN_REPOSITORY_NAME):
                main_repo_missing = True
            text2 += " * %s\n" % r

        if main_repo_missing:
            text = "This Supplemental Pack is not compatible with this version of %s." % version.PRODUCT_BRAND
        else:
            text = "The following dependencies have not yet been installed:\n\n" + text2 + \
                   "\nPlease install them first and try again."

        ButtonChoiceWindow(
            tui.screen, "Error",
            text,
            ['Back'])

        return LEFT_BACKWARDS

    def confirm_more_media(_):
        """ 'Really use this disc?' screen. """
        repos = repository.repositoriesFromDefinition('local', '')
        assert len(repos) > 0

        USE, VERIFY, BACK = range(3)
        default_button = VERIFY
        media_contents = []
        for r in repos:
            if r.identifier() in installed_repos:
                media_contents.append(" * %s (already installed)" % r.name())
                default_button = BACK
            else:
                media_contents.append(" * %s" % r.name())
        text = "The media you have inserted contains:\n\n" + "\n".join(media_contents)

        done = False
        while not done:
            ans = snackutil.ButtonChoiceWindowEx(tui.screen, "New Media", text, 
                                                 ['Use media', 'Verify media', 'Back'], 
                                                 width=50, default=default_button)
            
            if ans == 'verify media':
                tui.repo.interactive_source_verification('local', '', 'installation')
            elif ans == 'back':
                rc = LEFT_BACKWARDS
                done = True
            else:
                rc = RIGHT_FORWARDS
                done = True

        return rc

    seq = [ uicontroller.Step(get_more_media), uicontroller.Step(check_requires), uicontroller.Step(confirm_more_media) ]
    direction = uicontroller.runSequence(seq, {})
    return (direction == RIGHT_FORWARDS, direction != EXIT)
