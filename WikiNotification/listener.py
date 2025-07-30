# -*- coding: utf-8 -*-
# vim: sw=4 ts=4 fenc=utf-8
# =============================================================================
# $Id: listener.py 24 2007-10-26 15:58:00Z s0undt3ch $
# =============================================================================
#             $URL: http://wikinotification.ufsoft.org/svn/trunk/WikiNotification/listener.py $
# $LastChangedDate: 2007-10-26 16:58:00 +0100 (Fri, 26 Oct 2007) $
#             $Rev: 24 $
#   $LastChangedBy: s0undt3ch $
# =============================================================================
# Copyright (C) 2006 UfSoft.org - Pedro Algarvio <ufs@ufsoft.org>
#
# Please view LICENSE for additional licensing information.
# =============================================================================

import inspect
from trac.config import Option, BoolOption, ListOption, IntOption
from trac.core import *
from trac.notification.api import IEmailDecorator, INotificationFormatter, NotificationEvent, NotificationSystem
from trac.notification.mail import RecipientMatcher, create_charset, create_mime_multipart, create_mime_text, set_header
from trac.perm import PermissionSystem
from trac.resource import Resource
from trac.util.text import exception_to_unicode
from trac.util.translation import deactivate, reactivate
from trac.web.chrome import Chrome
from trac.wiki.api import IWikiChangeListener
# from .notification import WikiNotifyEmail


class WikiNotificationError(TracError):
    pass


class WikiNotificationChangeEvent(NotificationEvent):
    realm = 'wiki'

    def __init__(self, category, page, time, author):
        super(WikiNotificationChangeEvent, self).__init__(self.realm, category, page, time, author)
        # self.data = data


class WikiNotificationChangeListener(Component):
    """Class that listens for wiki changes."""
    implements(IWikiChangeListener)

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
        watching/un-watching a wiki page""")

    subject_template = Option(
        'wiki-notification', 'subject_template', '$prefix $pagename $action',
        "A Genshi text template snippet used to get the notification subject.")

    banned_addresses = ListOption(
        'wiki-notification', 'banned_addresses', [],
        doc="""A comma separated list of email addresses that should never be
        sent a notification email.""")

    # def __init__(self, *args, **kwargs):
    #     super(Component, self).__init__(*args, **kwargs)

    # Internal Methods
    def _get_req(self):
        """Grab req from the stack"""
        frame = inspect.currentframe()
        try:
            while frame.f_back:
                frame = frame.f_back
                request = frame.f_locals.get('req')
                if request:
                    self.env.log.debug(request)
                    return request
        finally:
            del frame
        return None

    def _send_notification(self, category, page, version, time, comment, author):
        event = WikiNotificationChangeEvent(category, page, time, author)
        subscriptions = self._subscriptions(event)
        try:
            NotificationSystem(self.env).distribute_event(event, subscriptions)
        except Exception as e:
            self.log.error("Failure sending notification for '%s' for page "
                           "%s: %s", category, page.name,
                           exception_to_unicode(e))
            raise WikiNotificationError(e)

    def _subscriptions(self, event):
        QUERY_SIDS = """SELECT sid from session_attribute
                        WHERE name=%s AND value LIKE %s"""
        transport_and_format = ('email', 'text/plain')
        matcher = RecipientMatcher(self.env)
        with self.env.db_query as db:
            cursor = db.cursor()
            cursor.execute(QUERY_SIDS, ('watched_pages', '%,' + event.page.name + ',%'))
            sids = cursor.fetchall()
            self.env.log.debug("SID'S TO NOTIFY: %s", sids)
            perm = PermissionSystem(self.env)
            resource = Resource('wiki', event.page.name)
            for sid in sids:
                if sid[0] != event.author and perm.check_permission(action='WIKI_VIEW', username=sid[0], resource=resource):
                    self.env.log.debug('SID: %s', sid[0])
                    recipient = matcher.match_recipient(sid[0])
                    if recipient:
                        yield recipient + transport_and_format

    # IWikiChangeListener methods
    def wiki_page_added(self, page):
        version, time, author, comment = page.get_history().next()
        self._send_notification('added', page, version, time, comment, author)
        # wne = WikiNotifyEmail(page.env)
        # wne.notify("added", page, version, time, comment, author, ipnr)

    def wiki_page_changed(self, page, version, time, comment, author):
        self._send_notification('modified', page, version, time, comment, author)
        # wne = WikiNotifyEmail(page.env)
        # wne.notify("modified", page, version, time, comment, author, ipnr)

    def wiki_page_deleted(self, page):
        req = self._get_req()
        author = req and req.authname or 'trac'
        self._send_notification('deleted', page, None, None, None, author)
        # wne = WikiNotifyEmail(page.env)
        # wne.notify("deleted", page, author=author)

    def wiki_page_version_deleted(self, page):
        req = self._get_req()
        author = req and req.authname or 'trac'
        version, _time, _author, _comment = page.get_history().next()
        self._send_notification('deleted_version', page, version+1, None, None, author)
        # wne = WikiNotifyEmail(page.env)
        # wne.notify("deleted_version", page, version=version +
        #            1, author=author)

    def wiki_page_renamed(self, page, old_name):
        req = self._get_req()
        author = req and req.authname or 'trac'
        redirect = req and req.args.get('redirect') or None
        self._watch_renamed_page(page.name, old_name)
        self._send_notification('renamed', page, None, None, None, author)
        # wne = WikiNotifyEmail(page.env)
        # wne.notify("renamed", page, author=author, ipnr=ipnr,
        #            redirect=redirect, old_name=old_name)

    def wiki_page_comment_modified(self, page, old_comment):
        pass

    def _watch_renamed_page(self, pagename, old_pagename):
        with self.env.db_transaction as db:
            cursor = db.cursor()
            cursor.execute("UPDATE session_attribute SET value=value || %s WHERE name=%s AND value LIKE %s AND value NOT LIKE %s",
                           ('%s,' % pagename, 'watched_pages', '%,' + old_pagename + ',%', '%,' + pagename + ',%'))


class WikiNotificationNotificationFormatter(Component):

    implements(IEmailDecorator, INotificationFormatter)

    realm = 'wiki'

    # IEmailDecorator methods

    def decorate_message(self, event, message, charset):
        if event.realm != self.realm:
            return

    # INotificationFormatter methods

    def get_supported_styles(self, transport):
        yield 'text/plain', self.realm

    def format(self, transport, style, event):
        if event.realm != self.realm:
            return
        data = dict()
        t = deactivate()
        try:
            return self._format_body(data, template_name)
        finally:
            reactivate(t)

    # Helper methods

    def _format_body(self, data, template_name):
        chrome = Chrome(self.env)
        data = chrome.populate_data(None, data)
        template = chrome.load_template(template_name, text=True)
        body =  chrome.render_template_string(template, data, text=True)
        return body.encode('utf-8')
