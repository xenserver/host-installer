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
import diskutil
from disktools import *
import version
import xmlrpclib

from snack import *

def runMainSequence(results, ram_warning, vt_warning, suppress_extra_cd_dialog):
    """ Runs the main installer sequence and updates results with a
    set of values ready for the backend. """
    uis = tui.installer.screens
    Step = uicontroller.Step

    def only_unupgradeable_products(answers):
        return len(answers['installed-products']) > 0 and \
               len(answers['upgradeable-products']) == 0 and \
               len(answers['backups']) == 0

    def upgrade_but_no_settings_predicate(answers):
        return answers['install-type'] == constants.INSTALL_TYPE_REINSTALL and \
            (not answers.has_key('installation-to-overwrite') or \
                 not answers['installation-to-overwrite'].settingsAvailable())

    has_multiple_nics = lambda a: len(a['network-hardware'].keys()) > 1

    is_reinstall_fn = lambda a: a['install-type'] == constants.INSTALL_TYPE_REINSTALL
    is_clean_install_fn = lambda a: a['install-type'] == constants.INSTALL_TYPE_FRESH
    is_not_restore_fn = lambda a: a['install-type'] != constants.INSTALL_TYPE_RESTORE
    is_using_remote_media_fn = lambda a: 'source-media' in a and a['source-media'] in ['url', 'nfs']

    def requires_backup(answers):
        return answers.has_key("installation-to-overwrite") and \
               upgrade.getUpgrader(answers['installation-to-overwrite']).requires_backup

    def optional_backup(answers):
        return answers.has_key("installation-to-overwrite") and \
               upgrade.getUpgrader(answers['installation-to-overwrite']).optional_backup

    def requires_repartition(answers):
        return 'installation-to-overwrite' in answers and \
           upgrade.getUpgrader(answers['installation-to-overwrite']).repartition

    def target_is_sr(answers):
        return 'target-is-sr' in answers and answers['target-is-sr']

    def target_no_space(answers):
        if 'primary-disk' in answers:
            tool = LVMTool()
            sr = tool.srPartition(answers['primary-disk'])
            if sr:
                return tool.deviceFreeSpace(sr) < 2 * constants.root_size * 2 ** 20
        return False

    def preserve_settings(answers):
        return answers.has_key('preserve-settings') and \
               answers['preserve-settings']
    not_preserve_settings = lambda a: not preserve_settings(a)

    def local_media_predicate(answers):
        if 'extra-repos' in answers:
            if True in map(lambda r: r[0] == 'local', answers['extra-repos']):
                return False
        return answers.has_key('source-media') and \
               answers['source-media'] == 'local' and not suppress_extra_cd_dialog

    def need_networking(answers):
        if 'source-media' in answers and \
               answers['source-media'] in ['url', 'nfs']:
            return True
        if 'installation-to-overwrite' in answers:
            settings = answers['installation-to-overwrite'].readSettings()
            return (settings['master'] != None)
        return False
        
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

    def out_of_order_pool_upgrade_fn(answers):
        if 'installation-to-overwrite' not in answers:
            return False

        ret = False
        settings = answers['installation-to-overwrite'].readSettings()
        if settings['master']:
            if not netutil.networkingUp():
                pass

            try:
                s = xmlrpclib.Server("http://"+settings['master'])
                session = s.session.slave_login("", settings['pool-token'])["Value"]
                pool = s.pool.get_all(session)["Value"][0]
                master = s.pool.get_master(session, pool)["Value"]
                software_version = s.host.get_software_version(session, master)["Value"]
                s.session.logout(session)

                # compare versions
                master_ver = product.Version.from_string(software_version['product_version'])
                if master_ver < product.THIS_PRODUCT_VERSION:
                    ret = True
            except:
                pass

        return ret

    if not results.has_key('install-type'):
        results['install-type'] = constants.INSTALL_TYPE_FRESH
        results['preserve-settings'] = False

    seq = [
        Step(uis.welcome_screen),
        Step(uis.eula_screen),
        Step(uis.hardware_warnings,
             args=[ram_warning, vt_warning],
             predicates=[lambda _:(ram_warning or vt_warning)]),
        Step(uis.overwrite_warning,
             predicates=[only_unupgradeable_products]),
        Step(uis.get_installation_type, 
             predicates=[lambda _:len(results['upgradeable-products']) > 0 or len(results['backups']) > 0]),
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
        Step(uis.select_primary_disk,
             predicates=[is_clean_install_fn]),
        Step(uis.check_sr_space,
             predicates=[target_is_sr, target_no_space]),
        Step(uis.repartition_existing,
             predicates=[is_reinstall_fn, requires_repartition]),
        Step(uis.select_guest_disks,
             predicates=[is_clean_install_fn]),
        Step(uis.confirm_erase_volume_groups,
             predicates=[is_clean_install_fn]),
        Step(tui.repo.select_repo_source,
             args=["Select Installation Source", "Please select the type of source you would like to use for this installation"],
             predicates=[is_not_restore_fn]),
        Step(uis.use_extra_media, args=[vt_warning],
             predicates=[local_media_predicate]),
        Step(uis.setup_runtime_networking, 
             predicates=[need_networking]),
        Step(uis.master_not_upgraded,
             predicates=[out_of_order_pool_upgrade_fn]),
        Step(tui.repo.get_source_location,
             args=[True],
             predicates=[is_using_remote_media_fn]),
        Step(tui.repo.verify_source, args=['installation', True], predicates=[is_not_restore_fn]),
        Step(uis.get_root_password,
             predicates=[is_not_restore_fn, not_preserve_settings]),
        Step(uis.get_admin_interface,
             predicates=[is_not_restore_fn, has_multiple_nics, not_preserve_settings]),
        Step(uis.get_admin_interface_configuration,
             predicates=[is_not_restore_fn, not_preserve_settings]),
        Step(uis.get_name_service_configuration,
             predicates=[is_not_restore_fn, not_preserve_settings]),
        Step(uis.get_timezone_region,
             predicates=[is_not_restore_fn, not_preserve_timezone]),
        Step(uis.get_timezone_city,
             predicates=[is_not_restore_fn, not_preserve_timezone]),
        Step(uis.get_time_configuration_method,
             predicates=[is_not_restore_fn, not_preserve_settings]),
        Step(uis.get_ntp_servers,
             predicates=[is_not_restore_fn, not_preserve_settings]),
        Step(uis.confirm_installation),
        ]
    return uicontroller.runSequence(seq, results)

def more_media_sequence(installed_repos, still_need):
    """ Displays the sequence of screens required to load additional
    media to install from.  installed_repos is a dictionary of repository
    IDs of repositories we already installed from, to help avoid
    issues where multiple CD drives are present.

    Returns tuple: (install more, then ask again, repo_list)"""
    Step = uicontroller.Step

    def get_more_media(_):
        """ 'Please insert disk' dialog. """
        done = False
        while not done:
            text = ''
            for need in still_need:
                if text == '':
                    text = "The following Supplemental Packs must be supplied to complete installation:\n\n"
                text += " * %s\n" % need
            text += "\nWhen there are no more Supplemental Packs to install press Skip."
            more = ButtonChoiceWindow(tui.screen, "New Media", "Please insert your Supplemental Pack now.\n" + text,
                                      ['Ok', 'Skip'], 40)
            if more == "skip":
                # they hit cancel:
                confirm = "skip"
                if len(still_need) > 0:
                    # check they mean it
                    check_text = "The following Supplemental Packs could contain packages which are essential:\n\n"
                    for need in still_need:
                        check_text += " * %s\n" % need
                    check_text += "\nAre you sure you wish to skip installing them?"
                    confirm = ButtonChoiceWindow(tui.screen, "Essential Packages", check_text,
                                                 ['Back', 'Skip'])
                if confirm == "skip":
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
            text = "This Supplemental Pack is not compatible with this version of %s." % (version.PRODUCT_BRAND or version.PLATFORM_NAME)
        else:
            text = "The following dependencies have not yet been installed:\n\n" + text2 + \
                   "\nPlease install them first and try again."

        ButtonChoiceWindow(
            tui.screen, "Error",
            text,
            ['Back'])

        return LEFT_BACKWARDS

    seq = [
        Step(get_more_media),
        Step(check_requires),
        Step(tui.repo.confirm_load_repo, args = ['Supplemental Pack', installed_repos])
        ]
    results = {}
    direction = uicontroller.runSequence(seq, results)
    return (direction == RIGHT_FORWARDS, direction != EXIT, 'repos' in results and results['repos'] or [])
