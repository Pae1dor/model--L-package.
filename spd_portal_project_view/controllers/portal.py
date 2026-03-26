from odoo import fields, http, _,conf
from odoo.addons.portal.controllers import portal
from odoo.addons.portal.controllers.portal import get_records_pager, pager as portal_pager
from odoo.exceptions import AccessError, MissingError
from odoo.http import request,route


class CustomerPortal(portal.CustomerPortal):
    _items_per_page = 20

    def _prepare_project_sharing_session_info(self, project, task=None):
        session_info = request.env['ir.http'].session_info()
        user_context = dict(request.env.context) if request.session.uid else {}
        mods = conf.server_wide_modules or []
        if request.env.lang:
            lang = request.env.lang
            session_info['user_context']['lang'] = lang
            # Update Cache
            user_context['lang'] = lang
        lang = user_context.get("lang")
        translation_hash = request.env['ir.http'].get_web_translations_hash(mods, lang)
        cache_hashes = {
            "translations": translation_hash,
        }
        # project_company = project.company_id or request.env.user.company_id
        project_company = self._get_project_sharing_company(project)
        session_info.update(
            cache_hashes=cache_hashes,
            action_name=project.action_project_project_sharing(),
            project_id=project.id,
            user_companies={
                'current_company': project_company.id,
                'allowed_companies': {
                    project_company.id: {
                        'id': project_company.id,
                        'name': project_company.name,
                    },
                },
            },
            currencies=request.env['ir.http'].get_currencies(),
        )
        if project:
            session_info['open_project_action'] = 'spd_portal_project_view.open_view_project_all_inherit'
        return session_info

    @http.route(['/my/projects', '/my/projects/page/<int:page>'], type='http', auth="user", website=True)
    def portal_my_projects(self, page=1, date_begin=None, date_end=None, sortby=None, **kw):
        if request.env.user.has_group('project.group_project_manager') :
            return request.render('spd_portal_project_view.project_sharing_portal', {})
        else:
            values = self._prepare_portal_layout_values()
            Project = request.env['project.project']
            domain = self._prepare_project_domain()

            searchbar_sortings = self._prepare_searchbar_sortings()
            if not sortby:
                sortby = 'date'
            order = searchbar_sortings[sortby]['order']

            if date_begin and date_end:
                domain += [('create_date', '>', date_begin), ('create_date', '<=', date_end)]

            # projects count
            project_count = Project.search_count(domain)
            # pager
            pager = portal_pager(
                url="/my/projects",
                url_args={'date_begin': date_begin, 'date_end': date_end, 'sortby': sortby},
                total=project_count,
                page=page,
                step=self._items_per_page
            )

            # content according to pager and archive selected
            projects = Project.search(domain, order=order, limit=self._items_per_page, offset=pager['offset'])
            request.session['my_projects_history'] = projects.ids[:100]

            values.update({
                'date': date_begin,
                'date_end': date_end,
                'projects': projects,
                'page_name': 'project',
                'default_url': '/my/projects',
                'pager': pager,
                'searchbar_sortings': searchbar_sortings,
                'sortby': sortby
            })
            return request.render("project.portal_my_projects", values)

    # Create our custom route for render project sharing template with session_info data
    @http.route("/my/projects/project_sharing", type="http", auth="user", methods=['GET'])
    def render_project_project_backend_view(self, project_id=None, task_id=None):
        project = request.env['project.project'].sudo().search([], limit=1)
        task = None
        return request.render(
            'spd_portal_project_view.project_project_sharing_embed',
            {'session_info': self._prepare_project_sharing_session_info(project, task)})

    # In this method prepare the value of session_info for task
    def _prepare_project_task_sharing_session_info(self, project, task=None):
        session_info = request.env['ir.http'].session_info()
        user_context = dict(request.env.context) if request.session.uid else {}
        mods = conf.server_wide_modules or []
        if request.env.lang:
            lang = request.env.lang
            session_info['user_context']['lang'] = lang
            # Update Cache
            user_context['lang'] = lang
        lang = user_context.get("lang")
        translation_hash = request.env['ir.http'].get_web_translations_hash(mods, lang)
        cache_hashes = {
            "translations": translation_hash,
        }

        project_company = self._get_project_sharing_company(project)

        session_info.update(
            cache_hashes=cache_hashes,
            action_name=project.action_project_sharing(),
            project_id=project.id,
            user_companies={
                'current_company': project_company.id,
                'allowed_companies': {
                    project_company.id: {
                        'id': project_company.id,
                        'name': project_company.name,
                    },
                },
            },
            # FIXME: See if we prefer to give only the currency that the portal user just need to see the correct information in project sharing
            currencies=request.env['ir.http'].get_currencies(),
        )
        if task:
            session_info['open_task_action'] = task.action_project_sharing_open_task()
        return session_info


    # Inherit the existing route for showing task in kanban view.
    @http.route(['/my/projects/<int:project_id>', '/my/projects/<int:project_id>/page/<int:page>'], type='http',
                auth="public", website=True)
    def portal_my_project(self, project_id=None, access_token=None, page=1, date_begin=None, date_end=None, sortby=None,
                          search=None, search_in='content', groupby=None, task_id=None, **kw):
        project = request.env['project.project'].sudo().browse(project_id)
        if not project.exists() or not project.with_user(request.env.user)._check_project_sharing_access():
            return request.not_found()
        task = task_id and request.env['project.task'].browse(int(task_id))
        if request.env.user.has_group('project.group_project_manager'):
            return request.render(
                'project.project_sharing_embed',
                {'session_info': self._prepare_project_task_sharing_session_info(project, task)},
            )
        else:
            try:
                project_sudo = self._document_check_access('project.project', project_id, access_token)
            except (AccessError, MissingError):
                return request.redirect('/my')
            if project_sudo.collaborator_count and project_sudo.with_user(
                    request.env.user)._check_project_sharing_access():
                values = {'project_id': project_id}
                if task_id:
                    values['task_id'] = task_id
                return request.render("project.project_sharing_portal", values)
            project_sudo = project_sudo if access_token else project_sudo.with_user(request.env.user)
            if not groupby:
                groupby = 'stage'
            values = self._project_get_page_view_values(project_sudo, access_token, page, date_begin, date_end, sortby,
                                                        search, search_in, groupby, **kw)
            return request.render("project.portal_my_project", values)
