# -*- coding: utf-8 -*-
# vim: sw=4 ts=4 fenc=utf-8
# =============================================================================
# $Id: notification.py 66 2008-03-14 09:02:03Z s0undt3ch $
# =============================================================================
#             $URL: http://wikinotification.ufsoft.org/svn/trunk/WikiNotification/notification.py $
# $LastChangedDate: 2008-03-14 09:02:03 +0000 (Fri, 14 Mar 2008) $
#             $Rev: 66 $
#   $LastChangedBy: s0undt3ch $
# =============================================================================
# Copyright (C) 2006 UfSoft.org - Pedro Algarvio <ufs@ufsoft.org>
#
# Please view LICENSE for additional licensing information.
# =============================================================================
from trac.core import *
from trac.config import Option, BoolOption, ListOption, IntOption


class WikiNotificationSystem(Component):
    """This class exists purely to define the configuration options.
    """
    from_email = Option(
        'wiki-notification', 'from_email', 'trac+wiki@localhost',
        """Sender address to use in notification emails.""")

    from_name = Option(
        'wiki-notification', 'from_name', None,
        """Sender name to use in notification emails.

        Defaults to project name.""")

    smtp_always_cc = ListOption(
        'wiki-notification', 'smtp_always_cc', [],
        doc="""Comma separated list of email address(es) to always send
        notifications to.

        Addresses can be seen by all recipients (Cc:).""")

    smtp_always_bcc = ListOption(
        'wiki-notification', 'smtp_always_bcc', [],
        doc="""Comma separated list of email address(es) to always send
        notifications to.

        Addresses do not appear publicly (Bcc:).""")

    use_public_cc = BoolOption(
        'wiki-notification', 'use_public_cc', False,
        """Recipients can see email addresses of other CC'ed recipients.

        If this option is disabled(the default),
        recipients are put on BCC.

        (values: 1, on, enabled, true or 0, off, disabled, false)""")

    attach_diff = BoolOption(
        'wiki-notification', 'attach_diff', False,
        """Send `diff`'s as an attachment instead of inline in email body.""")

    redirect_time = IntOption(
        'wiki-notification', 'redirect_time', 5,
        """The default seconds a redirect should take when
        watching/un-watching a wiki page.""")

    subject_template = Option(
        'wiki-notification', 'subject_template', '${prefix} ${pagename} ${action}',
        "A Jinja2 text template snippet used to get the notification subject.")

    banned_addresses = ListOption(
        'wiki-notification', 'banned_addresses', [],
        doc="""A comma separated list of email addresses that should never be
        sent a notification email.""")
