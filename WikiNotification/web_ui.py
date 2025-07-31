# -*- coding: utf-8 -*-
# vim: sw=4 ts=4 fenc=utf-8
# =============================================================================
# $Id: web_ui.py 40 2008-03-05 13:53:14Z s0undt3ch $
# =============================================================================
#             $URL: http://wikinotification.ufsoft.org/svn/trunk/WikiNotification/web_ui.py $
# $LastChangedDate: 2008-03-05 13:53:14 +0000 (Wed, 05 Mar 2008) $
#             $Rev: 40 $
#   $LastChangedBy: s0undt3ch $
# =============================================================================
# Copyright (C) 2006 UfSoft.org - Pedro Algarvio <ufs@ufsoft.org>
#
# Please view LICENSE for additional licensing information.
# =============================================================================

import re
from trac.core import *
from trac.util.html import tag
from trac.web.chrome import INavigationContributor, ITemplateProvider, add_script, add_script_data
from trac.web import IRequestHandler
from trac.web.api import IRequestFilter

from pkg_resources import resource_filename
# from importlib.resources import files


class WikiNotificationWebModule(Component):

    implements(INavigationContributor, IRequestHandler, ITemplateProvider,
               IRequestFilter)

    # ITemplateProvider methods
    def get_htdocs_dirs(self):
        yield 'wiki_notification', resource_filename(__name__, 'htdocs')

    def get_templates_dirs(self):
        resource_dir = resource_filename(__name__, 'templates')
        # resource_dir = str(files('WikiNotification').joinpath('templates'))
        return [resource_dir]

    # INavigationContributor methods
    def get_active_navigation_item(self, req):
        return 'notification'

    def get_navigation_items(self, req):
        if self.config.getbool('notification', 'smtp_enabled', False):
            if req.perm.has_permission('WIKI_VIEW'):
                yield('metanav', 'notification',
                      tag.a('My Notifications',
                            title="Wiki Pages Change Notifications",
                            href=req.href.notification()))

    # IRequestFilter methods

    def pre_process_request(self, handler):
        return handler

    def post_process_request(self, req, template, data, content_type):
        if template == 'wiki_view.html' and self.config.getbool('notification', 'smtp_enabled', False):
            self.log.debug("Adding (un)watch links.")
            page = req.path_info[6:] or 'WikiStart'
            watched = self._get_watched_pages(req)
            wiki_notification_data = {'href': req.href.notification(page)}
            if page in watched:
                wiki_notification_data['title'] = 'Un-Watch Page'
            else:
                wiki_notification_data['title'] = 'Watch Page'
            add_script(req, 'wiki_notification/wiki_notification.js')
            add_script_data(req, wiki_notification=wiki_notification_data)
        return template, data, content_type

    # IRequestHandler methods
    def match_request(self, req):
        match = re.match(r'^/notification(?:/(.*))?', req.path_info)
        if match:
            if match.group(1):
                req.args['notification.wikipage'] = match.group(1)
                self.log.debug('NOTIFICATION PAGE: %s',  match.group(1))
            return True

    def process_request(self, req):
        req.perm.require('WIKI_VIEW')

        if 'email' not in req.session:
            data = {'notification': {'error': True},
                    'prefs': {'url': req.href.prefs()}}
            return 'notification.html', data

        notification = {'wikiurl': req.href.wiki(),
                        'my_not_url': req.href.notification()}
        try:
            notification['redirect_time'] = req.session['watched_pages.redirect_time']
        except KeyError:
            notification['redirect_time'] = self.config.getint('wiki-notification', 'redirect_time', 5)

        wikipage = req.args.get('notification.wikipage', False)
        watched = self._get_watched_pages(req)
#        self.log.debug('WATCHED PAGES XX: %s', watched)
        if watched == ([''] or [u'']):
            watched = []
#        self.log.debug('WATCHED PAGES YY: %s', watched)
        if wikipage:
            if wikipage in watched:
                notification['action'] = 'unwatch'
                self._unwatch_page(req, wikipage)
            else:
                self._watch_page(req, wikipage)
                notification['action'] = 'watch'
            notification['wikipage'] = wikipage
            notification['redir'] = req.href.wiki(wikipage)
            notification['showlist'] = False
            notification['removelist'] = [wikipage]
        else:
            if req.method == 'POST' and req.args.get('remove'):
                sel = req.args.get('sel')
                sel = isinstance(sel, list) and sel or [sel]
                for wikipage in sel:
                    self._unwatch_page(req, wikipage)
                notification['redir'] = req.href.notification()
                notification['removelist'] = sel
                notification['action'] = 'unwatch'
            elif req.method == 'POST' and req.args.get('update'):
                notification['redirect_time'] = \
                    req.session['watched_pages.redirect_time'] = \
                    req.args.get('redirect_time')
                notification['showlist'] = True
                notification['list'] = watched
            else:
                notification['showlist'] = True
                notification['list'] = watched

        return 'notification.html', {'notification': notification}

    # Internal methods
    def _get_watched_pages(self, req):
        try:
            watched = req.session['watched_pages'].strip(',').split(',')
            self.log.debug('WATCHED PAGES: %s', watched)
            return watched
        except KeyError:
            return []

    def _watch_page(self, req, page):
        watched = self._get_watched_pages(req)
        watched.append(page)
        req.session['watched_pages'] = ',' + ','.join(watched) + ','
        self._cleanup_session(req)

    def _unwatch_page(self, req, page):
        watched = self._get_watched_pages(req)
        watched.remove(page)
        req.session['watched_pages'] = ',' + ','.join(watched) + ','
        self._cleanup_session(req)

    def _cleanup_session(self, req):
        try:
            if req.session['watched_pages'] == u',,':
                del(req.session['watched_pages'])
        except:
            pass
        req.session.save()
