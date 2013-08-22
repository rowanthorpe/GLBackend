# -*- coding: UTF-8
#
#   activation
#   **********
#
# Contain all the logic able to unlock/password recovery/activate an User
# (Only Receiver involved in this process, at the moment)

from twisted.internet.defer import inlineCallbacks

from globaleaks.handlers.base import BaseHandler
from globaleaks.handlers.authentication import transport_security_check
from globaleaks.rest import requests
from globaleaks.utils import log, pretty_date_time, l10n

from globaleaks.settings import transact
from globaleaks.models import *
from globaleaks.rest import errors


def serialize_user(user):
    user_desc = {
        'username' :user.username,
        'role' : user.role,
        'state' : user.state,
        'last_login' : pretty_date_time(user.last_login),
        'first_failed' : pretty_date_time(user.first_failed),
        'failed_login_count' : user.failed_login_count,
        'recovery_code' : user.recovery_code,
        'recovery_date' : pretty_date_time(user.recovery_date)
    }
    return user_desc

@transact
def get_user_status(store, check_code):
    """
    @param store:
    @param check_code:
    @return:

    This function is used to check the status of an user,
        return the serialized User entry or raise exception
        errors.UserNotFound
    """
    log.debug("Receiver code [%s]" % check_code)

    try:
        uobj = store.find(User, User.recovery_code == unicode(check_code)).one()
    except Exception as excep:
        log.err("Exception in Storm user recovery code: %s" % excep)
        raise errors.UserNotFound

    if not uobj:
        log.debug("Recovery code not found %s" % check_code)
        raise errors.UserNotFound

    return serialize_user(uobj)


@transact
def set_user_status(store, user_id, new_status):
    """
    @param user_id: a real User.id
    @param new_status: the new status assigned
    @return:

    This function is used when some code in the GLB need to
    deactivate/reactivate/restore the user
    """
    assert new_status in User._states, "wrong User.status request"

    try:
        uobj = store.find(User, User.id == unicode(user_id)).one()
    except Exception as excep:
        log.err("Invalid user id recovery code: %s" % excep)
        raise errors.UserNotFound

    return serialize_user(uobj)




class ActivationInstance(BaseHandler):

    @inlineCallbacks
    @transport_security_check('receiver')
    def get(self, user_code, *uriargs):

        answer = yield get_user_status(user_code)

        self.set_status(200)
        self.finish(answer)

    @inlineCallbacks
    @transport_security_check('receiver')
    def put(self, user_code, *uriargs):
        """
        """

        request = self.validate_message(self.request.body,
                                        requests.receiverActivationDesc)

        answer = yield get_user_status(request, user_code)

        # TODO check compare request/answer

        yield set_user_status()

        self.set_status(200)
        self.finish(answer)


