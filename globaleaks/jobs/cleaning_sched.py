# -*- coding: UTF-8
#   cleaning_sched
#   **************
#
# Implementation of the cleaning operations (delete incomplete submission,
# delete expired tips, etc)

import os
import sys

from twisted.internet.defer import inlineCallbacks

from globaleaks.settings import transact, transact_ro, GLSetting
from globaleaks.utils.utility import log, pretty_date_time, is_expired, iso2dateobj
from globaleaks.jobs.base import GLJob
from globaleaks.models import InternalTip, ReceiverFile, InternalFile, Comment

__all__ = ['APSCleaning']

@transact_ro
def get_tiptime_by_marker(store, marker):
    assert marker in InternalTip._marker

    itip_list = store.find(InternalTip, InternalTip.mark == marker)

    tipinfo_list = []
    for itip in itip_list:

        comment_cnt = store.find(Comment, Comment.internaltip_id == itip.id).count()
        files_cnt = store.find(InternalFile, InternalFile.internaltip_id == itip.id).count()

        if not itip.context:
            log.err("A Tip related to a not existent Context! This would not happen if delete on cascade is working")
            # And the removal is forced putting 1 second of life to the Tip.
            tip_timetolive = 1
            submission_timetolive = 1
        else:
            tip_timetolive = itip.context.tip_timetolive
            submission_timetolive = itip.context.submission_timetolive

        serialized_tipinfo = {
            'id': itip.id,
            'creation_date': pretty_date_time(itip.creation_date),
            'tip_life_seconds':  tip_timetolive,
            'submission_life_seconds':  submission_timetolive,
            'files': files_cnt,
            'comments': comment_cnt,
        }
        tipinfo_list.append(serialized_tipinfo)

    return tipinfo_list


@transact
def itip_cleaning(store, id):
    """
    @param id: aim for an InternalTip, and delete them.
    """
    tit = store.find(InternalTip, InternalTip.id == id).one()

    if not tit: # gtfo
        log.err("Requested invalid InternalTip id in itip_cleaning! %s" % id)
        return

    comments = store.find(Comment, Comment.internaltip_id == id)
    log.debug("[-] Removing %d comments, %d files from an InternalTip and %d rtips" %
        (tit.internalfiles.count(), comments.count(), tit.receivertips.count() ))

    for ifile in tit.internalfiles:
        abspath = os.path.join(GLSetting.submission_path, ifile.file_path)
        ifname = unicode(ifile.name)

        if not os.path.isfile(abspath):
            log.err("Unable to remove non existent internalfile %s (itip %s, internalfile %s(%d))" %
                (abspath, id, ifname, ifile.size))
        else:
            try:
                os.unlink(abspath)
            except OSError as excep:
                log.err("Unable to remove %s: %s" % (abspath, excep.strerror))

        rfiles = store.find(ReceiverFile, ReceiverFile.internalfile_id == ifile.id)
        for rfile in rfiles:
            # The following code must be bypassed if rfile.file_path == ifile.filepath
            if rfile.file_path == ifile.file_path:
                continue

            abspath = os.path.join(GLSetting.submission_path, rfile.file_path)
    
            if not os.path.isfile(abspath):
                log.err("Unable to remove non existent receiverfile %s (itip %s, internalfile %s(%d))" %
                    (abspath, id, ifname, ifile.size))
                continue
    
            try:
                os.unlink(abspath)
            except OSError as excep:
                log.err("Unable to remove %s: %s" % (abspath, excep.strerror))

    store.remove(tit)


@transact
def debug_count_itips_by_marker(store):
    info_list = []
    for marker in InternalTip._marker:
        single_info = {
            marker: store.find(InternalTip, InternalTip.mark == marker).count()
        }
        info_list.append(single_info)

    return info_list


class APSCleaning(GLJob):
    @staticmethod
    @inlineCallbacks
    def operation():
        """
        Goal of this function is to check all the submission not
        finalized, and, if the expiration time sets in the context has
        been reached, then clean the submission_gus along with the fields,
        and, if present, the uploaded folder/files.

        Second goal of this function, is to check all the InternalTip(s)
        and their expiration date, if match, remove that, all the folder,
        comment and tip related.
        """
        try:
            submissions = yield get_tiptime_by_marker(InternalTip._marker[0]) # Submission
            log.debug("(Cleaning routines) %d unfinished Submission are check if expired" % len(submissions))
            for submission in submissions:
                if is_expired(iso2dateobj(submission['creation_date']), seconds=submission['submission_life_seconds']):
                    log.info("Deleting an unfinalized Submission (creation date: %s) files %d" %
                             (submission['creation_date'], submission['files']) )
                    yield itip_cleaning(submission['id'])

            tips = yield get_tiptime_by_marker(InternalTip._marker[2]) # First
            log.debug("(Cleaning routines) %d Tips stored are check if expired" % len(tips))
            for tip in tips:
                if is_expired(iso2dateobj(tip['creation_date']), seconds=tip['tip_life_seconds']):
                    log.info("Deleting an expired Tip (creation date: %s) files %d comments %d" %
                             (tip['creation_date'], tip['files'], tip['comments']) )
                    yield itip_cleaning(tip['id'])

        except Exception as excep:
            log.err("Exception failure in submission/tip cleaning routine (%s)" % excep.message)
            sys.excepthook(*sys.exc_info())
