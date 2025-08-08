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
from email.mime.text import MIMEText
import inspect
from trac.core import *
from trac.notification.api import IEmailDecorator, INotificationFormatter, NotificationEvent, NotificationSystem
from trac.notification.mail import RecipientMatcher, set_header
from trac.perm import PermissionSystem
from trac.resource import Resource
from trac.util.text import exception_to_unicode
from trac.util.translation import deactivate, reactivate
from trac.versioncontrol.diff import unified_diff
from trac.web.chrome import Chrome
from trac.wiki.api import IWikiChangeListener
from trac.wiki.model import WikiPage


diff_header = """Index: {name}
=========================================================================
--- {name} (version: {oldversion})
+++ {name} (version: {version})
"""


class WikiNotificationError(TracError):
    pass


class WikiNotificationChangeEvent(NotificationEvent):
    realm = 'wiki'

    def __init__(self, category, page, time, author,
                 version=None, comment=None,
                 old_name=None, old_comment=None, redirect=False):
        super(WikiNotificationChangeEvent, self).__init__(self.realm, category, page, time, author)
        self.version = version
        self.comment = comment
        self.old_name = old_name
        self.old_comment = old_comment
        self.redirect = redirect
        self.all_emails = list()
        self.cc_emails = list()
        self.bcc_emails = list()


class WikiNotificationChangeListener(Component):
    """Class that listens for wiki changes.
    """

    implements(IWikiChangeListener)

    # IWikiChangeListener methods

    def wiki_page_added(self, page):
        # version, time, author, comment = page.get_history().next()
        version, time, author, comment = next(page.get_history())
        self._send_notification('added', page, version, time, comment, author)

    def wiki_page_changed(self, page, version, time, comment, author):
        self._send_notification('changed', page, version, time, comment, author)

    def wiki_page_deleted(self, page):
        req = self._get_req()
        author = req and req.authname or 'trac'
        self._send_notification('deleted', page, None, None, None, author)

    def wiki_page_version_deleted(self, page):
        req = self._get_req()
        author = req and req.authname or 'trac'
        # version, _time, _author, _comment = page.get_history().next()
        version, _time, _author, _comment = next(page.get_history())
        self._send_notification('version deleted', page, version+1, None, None, author)

    def wiki_page_renamed(self, page, old_name):
        req = self._get_req()
        author = req and req.authname or 'trac'
        redirect = req and req.args.get('redirect') or None
        self.log.info('self._watch_renamed_page("%s", "%s")', page.name, old_name)
        self._watch_renamed_page(page.name, old_name)
        self._send_notification('renamed', page, None, None, None, author, old_name=old_name, redirect=redirect)

    def wiki_page_comment_modified(self, page, old_comment):
        req = self._get_req()
        author = req and req.authname or 'trac'
        self._send_notification('comment modified', page, page.version, None, page.comment, author, old_comment=old_comment)

    # Internal Methods

    def _get_req(self):
        """Grab req from the stack.
        """
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

    def _send_notification(self, category, page, version, time, comment, author,
                           old_name=None, old_comment=None, redirect=False):
        event = WikiNotificationChangeEvent(category, page, time, author,
                                            version=version, comment=comment,
                                            old_name=old_name, old_comment=old_comment,
                                            redirect=redirect)
        subscriptions = self._subscriptions(event)
        try:
            NotificationSystem(self.env).distribute_event(event, subscriptions)
        except Exception as e:
            self.log.error("Failure sending notification for '%s' for page "
                           "%s: %s", category, page.name,
                           exception_to_unicode(e))
            raise WikiNotificationError(e)

    def _subscriptions(self, event):
        """Returns a list of tuples of ('sid', 'authenticated', 'email') + ('email', 'text/plain').
        """
        transport_and_format = ('email', 'text/plain')
        matcher = RecipientMatcher(self.env)
        perm = PermissionSystem(self.env)
        resource = Resource('wiki', event.target.name)
        notify_author = self.config.getbool('wiki-notification', 'notify_author')
        blacklist = self.config.getlist('wiki-notification', 'banned_addresses')
        smtp_always_cc = self.config.getlist('wiki-notification', 'smtp_always_cc')
        smtp_always_bcc = self.config.getlist('wiki-notification', 'smtp_always_bcc')
        subscribed_sids = self._db_subscriptions(event)
        recipients = list()
        for sid in subscribed_sids:
            if sid == event.author and not notify_author:
                self.log.info('Skipping notification of sid="%s"; notify_author=False.', sid)
                continue
            if not perm.check_permission(action='WIKI_VIEW', username=sid, resource=resource):
                self.log.info('Skipping notification of sid="%s"; permission denied.', sid)
                continue
            recipient = matcher.match_recipient(sid)
            if recipient is None:
                self.log.warning("Invalid sid in watched_pages: '%s'!", sid)
            else:
                self.log.debug('recipient = %s', recipient)
                if recipient[2] in blacklist:
                    self.log.info('Skipping notification of sid="%s"; email "%s" is blacklisted.', sid, recipient[2])
                else:
                    recipients.append(recipient + transport_and_format)
        for email in smtp_always_cc + smtp_always_bcc:
            recipient = matcher.match_recipient(email)
            if recipient is None:
                self.log.warning("Invalid email in smtp_always_(b)cc: '%s'!", email)
            else:
                self.log.debug('recipient = %s', recipient)
                if recipient[2] in blacklist:
                    self.log.info('Skipping notification; email "%s" is blacklisted.', recipient[2])
                else:
                    recipients.append(recipient + transport_and_format)
        deduplicate_email = dict()
        for r in recipients:
            if r[2] in deduplicate_email:
                dup_r = deduplicate_email[r[2]]
                self.log.debug('Duplicate recipient detected: %s', r)
                if r == deduplicate_email[r[2]]:
                    self.log.debug('Duplicate is identical to %s.', dup_r)
                else:
                    if r[0] and not dup_r[0]:
                        self.log.debug('Duplicate email has additional user information.')
                        deduplicate_email[r[2]] = r
                    elif r[1] > dup_r[1]:
                        self.log.debug('New recipient data is authenticated.')
                        deduplicate_email[r[2]] = r
                    else:
                        self.log.debug('No reason to prefer duplicate recipient, skipping.')
            else:
                deduplicate_email[r[2]] = r
        # Attach CC data to the event.
        return_recipients = list(deduplicate_email.values())
        event.all_emails = [r[2] for r in return_recipients]
        event.cc_emails = [e for e in event.all_emails if e in smtp_always_cc]
        event.bcc_emails = [e for e in event.all_emails if e in smtp_always_bcc]
        return return_recipients

    def _db_subscriptions(self, event):
        """Return a list of SIDs that are subscribed to a page.
        """
        QUERY_SIDS = """SELECT sid from session_attribute
                        WHERE name=%s AND value LIKE %s"""
        with self.env.db_query as db:
            cursor = db.cursor()
            cursor.execute(QUERY_SIDS, ('watched_pages', '%,' + event.target.name + ',%'))
            sids = cursor.fetchall()
            self.log.debug("SIDs to notify: %s", sids)
            return_sids = [sid[0] for sid in sids]
        return return_sids

    def _watch_renamed_page(self, pagename, old_pagename):
        self.log.info("UPDATE session_attribute SET value=value || %s WHERE name=%s AND value LIKE %s AND value NOT LIKE %s",
                      f'{pagename},', 'watched_pages', f'%,{old_pagename},%', f'%,{pagename},%')
        with self.env.db_transaction as db:
            cursor = db.cursor()
            cursor.execute("UPDATE session_attribute SET value=value || %s WHERE name=%s AND value LIKE %s AND value NOT LIKE %s",
                           (f'{pagename},', 'watched_pages', f'%,{old_pagename},%', f'%,{pagename},%'))


class WikiNotificationNotificationFormatter(Component):
    implements(IEmailDecorator, INotificationFormatter)

    realm = 'wiki'
    template_name = "wiki_notification_email_template.txt"

    # IEmailDecorator methods

    def decorate_message(self, event, message, charset):
        if event.realm != self.realm:
            return
        # Set the subject
        subject = self._format_subject(event)
        set_header(message, 'Subject', subject, charset)
        # Set CC, etc.
        public_cc = self.config.getbool('wiki-notification', 'use_public_cc')
        if public_cc:
            self.log.debug('public_cc is True')
            self.log.debug('event.all_emails = %s', event.all_emails)
            self.log.debug('event.bcc_emails = %s', event.bcc_emails)
            public_cc_emails = [e for e in event.all_emails if e not in event.bcc_emails]
            self.log.debug('public_cc_emails = %s', public_cc_emails)
            if len(public_cc_emails) > 0:
                set_header(message, 'To', public_cc_emails[0], charset)
                if len(public_cc_emails) > 1:
                    set_header(message, 'Cc', ', '.join(public_cc_emails[1:]), charset)
        else:
            self.log.debug('public_cc is False')
            if event.cc_emails:
                self.log.debug('event.cc_emails = %s', event.cc_emails)
                set_header(message, 'Cc', ', '.join(event.cc_emails), charset)
        # Attach diff, if configured that way.
        attach_diff = self.config.getbool('wiki-notification', 'attach_diff')
        if event.category == 'changed' and attach_diff:
            wikidiff = self._obtain_diff(event)
            diffname = event.target.name.replace('/', '_')
            part = MIMEText(wikidiff.encode('utf-8'), 'x-diff', charset)
            part['Content-Disposition'] = f'attachment; filename={diffname}.diff'
            message.attach(part)

    # INotificationFormatter methods

    def get_supported_styles(self, transport):
        yield 'text/plain', self.realm

    def format(self, transport, style, event):
        if event.realm != self.realm:
            return
        t = deactivate()
        try:
            return self._format_body(event)
        finally:
            reactivate(t)

    # Helper methods

    def _format_body(self, event):
        format_data = dict()
        format_data['action'] = event.category
        format_data['author'] = event.author
        format_data['name'] = event.target.name
        format_data['comment'] = event.comment
        format_data['old_name'] = event.old_name
        format_data['old_comment'] = event.old_comment
        format_data['redirect'] = event.redirect
        format_data['text'] = event.target.text
        format_data['link'] = self.env.abs_href.wiki(event.target.name)
        format_data['linkdiff'] = self.env.abs_href.wiki(event.target.name, action='diff',
                                                         version=event.target.version)
        format_data['version'] = event.target.version
        attach_diff = self.config.getbool('wiki-notification', 'attach_diff')
        if attach_diff:
            format_data['wikidiff'] = None
        else:
            format_data['wikidiff'] = self._obtain_diff(event)
        chrome = Chrome(self.env)
        data = chrome.populate_data(None, format_data)
        template = chrome.load_template(self.template_name, text=True)
        body = chrome.render_template_string(template, data, text=True)
        return body.encode('utf-8')

    def _format_subject(self, event):
        template = self.config.get('wiki-notification', 'subject_template')
        prefix = self.config.get('notification', 'smtp_subject_prefix')
        if prefix == '__default__':
            prefix = f"[{self.config.get('project', 'name')}]"
        data = {'pagename': event.old_name or event.target.name,
                'prefix': prefix,
                'action': event.category,
                'env': self.env}
        return template.format(**data)

    def _obtain_diff(self, event):
        if event.category == 'changed' and event.target.version > 0:
            diff = diff_header.format(name=event.target.name,
                                      version=event.target.version,
                                      oldversion=event.target.version-1)
            oldpage = WikiPage(self.env, event.target.name, event.target.version - 1)
            for line in unified_diff(oldpage.text.splitlines(),
                                     event.target.text.splitlines(), context=3):
                diff += f"{line}\n"
            return diff
        return None
