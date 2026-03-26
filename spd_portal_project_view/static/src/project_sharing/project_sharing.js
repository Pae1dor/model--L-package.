/** @odoo-module **/

import { useBus, useService } from '@web/core/utils/hooks';
import { ActionContainer } from '@web/webclient/actions/action_container';
import { MainComponentsContainer } from "@web/core/main_components_container";
import { useOwnDebugContext } from "@web/core/debug/debug_context";
import { session } from '@web/session';
import { Component, markup, useEffect, useExternalListener, useState } from "@odoo/owl";
export class ProjectProjectSharingWebClient extends Component {
    setup() {
        window.parent.document.body.style.margin = "0";
        this.actionService = useService('action');
        this.user = useService("user");
        useOwnDebugContext({ categories: ["default"] });
        this.state = useState({
            fullscreen: false,
        });
        useBus(this.env.bus, "ACTION_MANAGER:UI-UPDATED", (mode) => {
            if (mode !== "new") {
                this.state.fullscreen = mode === "fullscreen";
            }
        });
        useEffect(
            () => {
                this._showView();
            },
            () => []
        );
        useExternalListener(window, "click", this.onGlobalClick, { capture: true });
    }

    async _showView() {
        const { action_name, project_id, open_project_action } = session;
        if (action_name.help) {
            action_name.help = markup(action_name.help);
        }
        await this.actionService.doAction(
            action_name,
            {
                clearBreadcrumbs: true,
                additionalContext: {
                    active_id: project_id,
                }
            }
        );
        if (open_project_action) {
            await this.actionService.doAction(open_project_action);
        }
    }

    /**
     * @param {MouseEvent} ev
     */
    onGlobalClick(ev) {
        // When a ctrl-click occurs inside an <a href/> element
        // we let the browser do the default behavior and
        // we do not want any other listener to execute.

        if (
            ev.ctrlKey &&
            ((ev.target instanceof HTMLAnchorElement && ev.target.href) ||
                (ev.target instanceof HTMLElement && ev.target.closest("a[href]:not([href=''])")))
        ) {
            ev.stopImmediatePropagation();
            return;
        }
    }
}

ProjectProjectSharingWebClient.props = {};
ProjectProjectSharingWebClient.components = { ActionContainer, MainComponentsContainer };
ProjectProjectSharingWebClient.template = 'spd_portal_project_view.ProjectProjectSharingWebClient';