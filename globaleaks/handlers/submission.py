# -*- coding: UTF-8
#   submission
#   **********
#
#   Implements a GlobaLeaks submission, then the operations performed
#   by an HTTP client in /submission URI

from twisted.internet.defer import inlineCallbacks

from globaleaks.settings import transact, transact_ro, GLSetting
from globaleaks.models import *
from globaleaks import security
from globaleaks.handlers.base import BaseHandler
from globaleaks.handlers.authentication import transport_security_check, unauthenticated
from globaleaks.rest import requests
from globaleaks.utils.utility import log, utc_future_date, pretty_date_time, datetime_now
from globaleaks.utils.structures import Fields
from globaleaks.third_party import rstr
from globaleaks.rest import errors


def wb_serialize_internaltip(internaltip):
    response = {
        'id' : unicode(internaltip.id),
        # compatibility! until client is not patched.
        'submission_gus' : unicode(internaltip.id),
        'context_gus': unicode(internaltip.context_id),
        'creation_date' : unicode(pretty_date_time(internaltip.creation_date)),
        'expiration_date' : unicode(pretty_date_time(internaltip.expiration_date)),
        'wb_fields' : dict(internaltip.wb_fields or {}),
        'download_limit' : int(internaltip.download_limit),
        'access_limit' : int(internaltip.access_limit),
        'mark' : unicode(internaltip.mark),
        'pertinence' : unicode(internaltip.pertinence_counter),
        'escalation_threshold' : unicode(internaltip.escalation_threshold),
        'files' : [],
        'receivers' : []
    }
    for receiver in internaltip.receivers:
        response['receivers'].append(receiver.id)

    for internalfile in internaltip.internalfiles:
        response['files'].append(internalfile.id)

    return response

@transact
def create_whistleblower_tip(store, submission_desc):
    """
    The plaintext receipt is returned only now, and then is
    stored hashed in the WBtip table
    """
    from Crypto import Random
    Random.atfork()

    assert submission_desc is not None and submission_desc.has_key('id')

    wbtip = WhistleblowerTip()

    context = store.find(Context, Context.id == submission_desc['context_gus']).one()

    return_value_receipt = unicode( rstr.xeger(context.receipt_regexp) )
    node = store.find(Node).one()
    wbtip.receipt_hash = security.hash_password(return_value_receipt, node.receipt_salt)

    wbtip.access_counter = 0
    wbtip.internaltip_id = submission_desc['id']
    store.add(wbtip)

    return return_value_receipt


# Remind: it's a store without @transaction because called by a @ŧransact
def import_receivers(store, submission, receiver_id_list, required=False):
    context = submission.context

    # As first we check if Context has some policies
    if not context.selectable_receiver:
        for receiver in context.receivers:
            # Add only the receiver not yet associated in Many-to-Many
            check = store.find(ReceiverInternalTip,
                ( ReceiverInternalTip.receiver_id == receiver.id,
                  ReceiverInternalTip.internaltip_id == submission.id) ).one()
            if not check:
                submission.receivers.add(receiver)

        store.commit()

        reloaded_submission = store.find(InternalTip, InternalTip.id == submission.id).one()
        log.debug("Context [%s] has a fixed receivers corpus #%d SID = %s" %
                (reloaded_submission.context.name[GLSetting.memory_copy.default_language],
                 reloaded_submission.receivers.count(), submission.id) )
        return

    # Clean the previous list of selected Receiver
    for prevrec in submission.receivers:
        try:
            submission.receivers.remove(prevrec)
        except Exception as excep:
            log.err("Unable to remove receiver from Tip, before new reassignment")
            raise excep

    store.commit()

    # without contexts policies, import WB requests and checks consistency
    sorted_receiver_id_list = list(set(receiver_id_list))
    for receiver_id in sorted_receiver_id_list:
        try:
            receiver = store.find(Receiver, Receiver.id == unicode(receiver_id)).one()
        except Exception as excep:
            log.err("Receiver requested (%s) can't be found: %s" %
                    (receiver_id, excep))
            raise errors.ReceiverGusNotFound

        if not context in receiver.contexts:
            raise errors.InvalidInputFormat("Forged receiver selection, you fuzzer! <:")

        try:
            submission.receivers.add(receiver)
        except Exception as excep:
            log.err("Receiver %s can't be assigned to the tip [%s]" % (receiver_id, excep) )
            continue

        log.debug("+receiver [%s] In tip (%s) #%d" %\
                (receiver.name, submission.id, submission.receivers.count() ) )

    if required and submission.receivers.count() == 0:
        log.err("Receivers required to be selected, not empty")
        raise errors.SubmissionFailFields("Needed almost one Receiver selected")


# Remind: it's a store without @transaction because called by a @ŧransact
def import_files(store, submission, files, finalize):
    """
    @param submission: the Storm obj
    @param files: the list of InternalFiles UUIDs
    @return:
        Look if all the files specified in the list exist,
        Look if the context *require* almost a file, raise
            an error if missed
    """
    for file_id in files:
        try:
            ifile = store.find(InternalFile, InternalFile.id == unicode(file_id)).one()
        except Exception as excep:
            log.err("Storm error, not found %s file in import_files (%s)" %
                    (file_id, excep))
            raise errors.FileGusNotFound

        ifile.internaltip_id = submission.id
    
    if finalize and submission.context.file_required and not len(files):
        log.debug("Missing file for a submission in context %s" %
                  submission.context.name)
        raise errors.FileRequiredMissing

    # commit before return
    store.commit()


@transact
def create_submission(store, request, finalize, language=GLSetting.memory_copy.default_language):

    context = store.find(Context, Context.id == unicode(request['context_gus'])).one()
    if not context:
        log.err("Context requested: [%s] not found!" % request['context_gus'])
        raise errors.ContextGusNotFound

    submission = InternalTip()

    submission.escalation_threshold = context.escalation_threshold
    submission.access_limit = context.tip_max_access
    submission.download_limit = context.file_max_download
    submission.expiration_date = utc_future_date(seconds=context.tip_timetolive)
    submission.pertinence_counter = 0
    submission.context_id = context.id
    submission.creation_date = datetime_now()

    if finalize:
        submission.mark = InternalTip._marker[1] # Finalized
    else:
        submission.mark = InternalTip._marker[0] # Submission

    try:
        store.add(submission)
    except Exception as excep:
        log.err("Storm/SQL Error: %s (create_submission)" % excep)
        raise errors.InternalServerError("Unable to commit on DB")

    files = request.get('files', [])
    try:
        import_files(store, submission, files, finalize)
    except Exception as excep:
        log.err("Submission create: files import fail: %s" % excep)
        store.remove(submission)
        store.commit()
        raise excep

    wb_fields = request.get('wb_fields', {})
    try:
        fo = Fields(context.localized_fields, context.unique_fields)
        fo.validate_fields(wb_fields, strict_validation=finalize)
        submission.wb_fields = wb_fields
    except Exception as excep:
        log.err("Submission create: fields validation fail: %s" % excep)
        store.remove(submission)
        store.commit()
        raise excep

    receivers = request.get('receivers', [])
    try:
        import_receivers(store, submission, receivers, required=finalize)
    except Exception as excep:
        log.err("Submission reate: receivers import fail: %s" % excep)
        store.remove(submission)
        store.commit()
        raise excep

    submission_dict = wb_serialize_internaltip(submission)
    return submission_dict

@transact
def update_submission(store, id, request, finalize, language=GLSetting.memory_copy.default_language):

    context = store.find(Context, Context.id == unicode(request['context_gus'])).one()
    if not context:
        log.err("Context requested: [%s] not found!" % request['context_gus'])
        raise errors.ContextGusNotFound

    submission = store.find(InternalTip, InternalTip.id == unicode(id)).one()

    if not submission:

        log.debug("Creating a new submission in update!")
        submission = InternalTip()

        submission.escalation_threshold = context.escalation_threshold
        submission.access_limit = context.tip_max_access
        submission.download_limit = context.file_max_download
        submission.expiration_date = utc_future_date(seconds=context.tip_timetolive)
        submission.pertinence_counter = 0
        submission.context_id = context.id
        submission.creation_date = datetime_now()
        submission.mark = InternalTip._marker[0] # Submission

        try:
            store.add(submission)
        except Exception as excep:
            log.err("Storm/SQL Error: %s (update_submission)" % excep)
            raise errors.InternalServerError("Unable to commit on DB")

    # this may happen if a submission try to update a context
    if submission.context_id != context.id:
        log.err("Can't be changed context in a submission update")
        raise errors.ContextGusNotFound("Context are immutable")

    if submission.mark != InternalTip._marker[0]:
        log.err("Submission %s do not permit update (status %s)" % (id, submission.mark))
        raise errors.SubmissionConcluded

    files = request.get('files', [])
    try:
        import_files(store, submission, files, finalize)
    except Exception as excep:
        log.err("Submission update: files import fail: %s" % excep)
        log.exception(excep)
        raise excep

    wb_fields = request.get('wb_fields', [])
    try:
        fo = Fields(context.localized_fields, context.unique_fields)
        fo.validate_fields(wb_fields, strict_validation=finalize)
        submission.wb_fields = wb_fields
    except Exception as excep:
        log.err("Submission update: fields validation fail: %s" % excep)
        log.exception(excep)
        raise excep

    receivers = request.get('receivers', [])
    try:
        import_receivers(store, submission, receivers, required=finalize)
    except Exception as excep:
        log.err("Submission update: receiver import fail: %s" % excep)
        log.exception(excep)
        raise excep

    if finalize:
        submission.mark = InternalTip._marker[1] # Finalized

    submission_dict = wb_serialize_internaltip(submission)
    return submission_dict


@transact_ro
def get_submission(store, id):
    submission = store.find(InternalTip, InternalTip.id == unicode(id)).one()
    if not submission:
        log.err("Invalid Submission requested %s in GET" % id)
        raise errors.SubmissionGusNotFound

    return wb_serialize_internaltip(submission)

@transact
def delete_submission(store, id):
    submission = store.find(InternalTip, InternalTip.id == unicode(id)).one()

    if not submission:
        log.err("Invalid Submission requested %s in DELETE" % id)
        raise errors.SubmissionGusNotFound

    if submission.mark != submission._marked[0]:
        log.err("Submission %s already concluded (status: %s)" % (id, submission.mark))
        raise errors.SubmissionConcluded

    store.remove(submission)


class SubmissionCreate(BaseHandler):
    """
    U2
    This class create the submission, receiving a partial wbSubmissionDesc, and
    returning a submission_gus, usable in update operation.
    """

    @transport_security_check('submission')
    @unauthenticated
    @inlineCallbacks
    def post(self, *uriargs):
        """
        Request: wbSubmissionDesc
        Response: wbSubmissionDesc
        Errors: ContextGusNotFound, InvalidInputFormat, SubmissionFailFields

        This creates an empty submission for the requested context,
        and returns submissionStatus with empty fields and a Submission Unique String,
        This is the unique token used during the submission procedure.
        sessionGUS is used as authentication secret for the next interaction.
        expire after the time set by Admin (Context dependent setting)
        """
        request = self.validate_message(self.request.body, requests.wbSubmissionDesc)

        if request['finalize']:
            finalize = True
        else:
            finalize = False

        status = yield create_submission(request, finalize)

        if finalize:
            receipt = yield create_whistleblower_tip(status)
            status.update({'receipt': receipt})
        else:
            status.update({'receipt' : ''})

        self.set_status(201) # Created
        self.finish(status)


class SubmissionInstance(BaseHandler):
    """
    U3
    This is the interface for create, populate and complete a submission.
    Relay in the client-server update and exchange of the submissionStatus message.
    """

    @transport_security_check('submission')
    @unauthenticated
    @inlineCallbacks
    def get(self, submission_gus, *uriargs):
        """
        Parameters: submission_gus
        Response: wbSubmissionDesc
        Errors: SubmissionGusNotFound, InvalidInputFormat

        Get the status of the current submission.
        """
        submission = yield get_submission(submission_gus)

        self.set_status(200)
        self.finish(submission)

    @transport_security_check('submission')
    @unauthenticated
    @inlineCallbacks
    def put(self, submission_gus, *uriargs):
        """
        Parameter: submission_gus
        Request: wbSubmissionDesc
        Response: wbSubmissionDesc
        Errors: ContextGusNotFound, InvalidInputFormat, SubmissionFailFields, SubmissionGusNotFound, SubmissionConcluded

        PUT update the submission and finalize if requested.
        """
        request = self.validate_message(self.request.body, requests.wbSubmissionDesc)

        if request['finalize']:
            finalize = True
        else:
            finalize = False

        status = yield update_submission(submission_gus, request, finalize, self.request.language)

        if finalize:
            receipt = yield create_whistleblower_tip(status)
            status.update({'receipt': receipt})
        else:
            status.update({'receipt' : ''})

        self.set_status(202) # Updated
        self.finish(status)


    @transport_security_check('submission')
    @unauthenticated
    @inlineCallbacks
    def delete(self, submission_gus, *uriargs):
        """
        Parameter: submission_gus
        Request:
        Response: None
        Errors: SubmissionGusNotFound, SubmissionConcluded

        A whistleblower is deleting a Submission because has understand that won't really be an hero. :P
        """

        yield delete_submission(submission_gus)

        self.set_status(200) # Accepted
        self.finish()

