#! -*- coding : utf-8 -*-

# Integration of Zope (4) with Sentry
# The code below is heavily based on the raven.contrib. zope module

import os
import re
import logging
import sentry_sdk
import sentry_sdk.utils as sentry_utils

from App.config import getConfiguration
from zope.component import adapter
from zope.globalrequest import getRequest
from AccessControl.users import nobody
from ZPublisher.interfaces import IPubFailure
from ZPublisher.HTTPRequest import _filterPasswordFields
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.logging import ignore_logger

sentry_dsn = os.environ.get("SENTRY_DSN")

sentry_project = os.environ.get("SENTRY_PROJECT")

is_sentry_optional = os.environ.get("SENTRY_OPTIONAL")

sentry_max_length = os.environ.get("SENTRY_MAX_LENGTH")

ignore_logger("Zope.SiteErrorLog")

LOG = logging.getLogger('unimr.SiteErrorLog')

def _before_send(event, hint):
    """
     Inject Plone/Zope specific information (based on raven.contrib.zope)
    """

    request = getRequest()
    if not request:
        return event

    # print("--------------------")
    # for attr, value in event.items():
    #     if(attr == 'modules'):
    #         continue
    #     print(attr, value)
    # print("--------------------")

    # print("++++++++++")
    # for attr, value in hint.items():
    #     print(attr, value)
    # print("++++++++++")
    # for attr, value in hint['log_record'].__dict__.items():
    #     print(attr, value)
    # print("++++++++++")

    msg = hint['log_record'].getMessage()
    searchObj = re.search('(zExceptions.)[^:]+', msg)

    if searchObj:
        fingerprint = searchObj.group()
        print("fingerprint: {}".format(fingerprint))
        event['fingerprint'] = [
            '{{ default }}',
            fingerprint
        ]
    # else:
    #     event['fingerprint'] = [
    #         '{{ default }}',
    #         'other'
    #     ]

    # ensure that all header key-value pairs are strings
    headers = dict()
    for k, v in request.environ.items():
        if not isinstance(v, str):
            v = str(v)
        headers[k] = v

    body_pos = request.stdin.tell()
    request.stdin.seek(0)
    body = request.stdin.read()
    request.stdin.seek(body_pos)
    http = dict(
        headers=headers,
        url=request.getURL(),
        method=request.method,
        host=request.environ.get("REMOTE_ADDR", ""),
    )
    if "HTTP_USER_AGENT" in http["headers"]:
        if "User-Agent" not in http["headers"]:
            http["headers"]["User-Agent"] = http["headers"]["HTTP_USER_AGENT"]
    if "QUERY_STRING" in http["headers"]:
        http["query_string"] = http["headers"]["QUERY_STRING"]

    event["extra"]["request"] = http

    event["extra"]["form"] = {}
    event["extra"]["other"] = {}
    event["extra"]["cookies"] = {}
    event["extra"]["lazy items"] = {}

    for k, v in _filterPasswordFields(request.form.items()):
        event["extra"]["form"][k] = repr(v)

    for k, v in _filterPasswordFields(request.cookies.items()):
        event["extra"]["cookies"][k] = repr(v)

    for k, v in _filterPasswordFields(request._lazies.items()):
        event["extra"]["lazy items"][k] = repr(v)

    for k, v in _filterPasswordFields(request.other.items()):
        if k in ('PARENTS', 'RESPONSE'):
            continue
        event["extra"]["other"][k] = repr(v)

    user = request.get("AUTHENTICATED_USER", None)
    if user is not None and user != nobody:
        user_dict = {
            "id": user.getId(),
            "email": user.getProperty("email") or "",
        }
    else:
        user_dict = {}
    event["extra"]["user"] = user_dict

    return event


def before_send(event, hint):
    try:
        return _before_send(event, hint)
    except KeyError:
        logging.warning("Could not extract data from request", exc_info=True)


if not sentry_dsn:
    msg = "Environment variable SENTRY_DSN not configured"
    if is_sentry_optional:
        logging.info(msg)
    else:
        raise RuntimeError(msg)

if sentry_dsn:
    if sentry_max_length:
        try:
            sentry_max_length = int(sentry_max_length)
        except ValueError:
            msg = "Environment variable SENTRY_MAX_LENGTH is malformed"
            raise RuntimeError(msg)
        else:
            sentry_utils.MAX_STRING_LENGTH = sentry_max_length
    sentry_logging = LoggingIntegration(
        level=logging.INFO,        # Capture info and above as breadcrumbs
        event_level=logging.ERROR,  # Send errors as events
    )

    sentry_sdk.init(
        sentry_dsn,
        max_breadcrumbs=50,
        before_send=before_send,
        debug=True,
        attach_stacktrace=True
    )

    configuration = getConfiguration()
    tags = {}
    instancehome = configuration.instancehome
    tags['instance_name'] = instancehome.rsplit(os.path.sep, 1)[-1]

    with sentry_sdk.configure_scope() as scope:
        for k, v in tags.items():
            scope.set_tag(k, v)
        if sentry_project:
            scope.set_tag("project", sentry_project)

    logging.info("Sentry integration enabled")


# fake registration in order to import the file properly
# for the sentry_skd.init() call
@adapter(IPubFailure)
def dummy(event):
    print("********************")
    print("dummy")
    print(event)
    print("---------------")
    for attr, value in event.__dict__.items():
        if(attr == 'modules'):
            continue
        print(attr, value)
    print("--------------")
    print("********************")
    logging.exception("TEST", exc_info=event.exc_info)
    # sentry_sdk.capture_exception(event.exc_info)
