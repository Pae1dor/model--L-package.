import json
from odoo import http, fields
from odoo.http import request, Response


class PosAPI(http.Controller):

    @http.route(
        "/api/pos/list",
        type="http",
        methods=["GET"],
        auth="public",
        cors="*",
        csrf=False,
    )
    def pos_list(self, **kwargs):
        try:
            q = request.params.get("q")

            domain = [
                ("state", "=", "posted"),
                ("move_type", "=", "entry"),
                ("date", "=", fields.Date.context_today(request.env.user)),
            ]

            # Check if auto_post exists on account.move
            if "auto_post" in request.env["account.move"]._fields:
                domain.append(("auto_post", "=", "no"))

            if q:
                domain.append("|")
                domain.append(("name", "ilike", "%" + q + "%"))
                domain.append(("invoice_partner_display_name", "ilike", "%" + q + "%"))

            moves = request.env["account.move"].sudo().search(domain)

            rows = []
            for am in moves:
                lines = []
                for aml in am.line_ids:
                    state = aml.parent_state
                    account_id = aml.account_id.id
                    if state == "posted":
                        # In Odoo 15+, analytic_account_id is replaced by analytic_distribution JSON
                        analytic_name = "-"
                        if (
                            hasattr(aml, "analytic_distribution")
                            and aml.analytic_distribution
                        ):
                            first_acc_id = list(aml.analytic_distribution.keys())[0]
                            # Try to find corresponding Project
                            project = (
                                request.env["project.project"]
                                .sudo()
                                .search(
                                    [("analytic_account_id", "=", int(first_acc_id))],
                                    limit=1,
                                )
                            )
                            if project:
                                analytic_name = project.name
                            else:
                                acc = (
                                    request.env["account.analytic.account"]
                                    .sudo()
                                    .browse(int(first_acc_id))
                                )
                                if acc.exists():
                                    analytic_name = acc.name

                        lines.append(
                            {
                                "name": aml.name or "",
                                "partner_name": (
                                    aml.partner_id.name if aml.partner_id else None
                                ),
                                "account_id": account_id,
                                "debit": aml.debit,
                                "credit": aml.credit,
                                "analytic_discount": getattr(
                                    aml, "analytic_discount", analytic_name
                                ),
                                "move_id": aml.id,
                                "line_invoice_date_due": (
                                    str(am.invoice_date_due)
                                    if getattr(am, "invoice_date_due", None)
                                    else None
                                ),
                            }
                        )

                rows.append(
                    {
                        "id": am.id,
                        "total": am.amount_total,
                        "amount_tax": getattr(am, "amount_tax", 0.0),
                        "amount_untaxed": getattr(am, "amount_untaxed", 0.0),
                        "invoice_partner_display_name": getattr(
                            am, "invoice_partner_display_name", ""
                        ),
                        "seq_prefix": am.journal_id.code if am.journal_id else "POS",
                        "account_move_name": am.name,
                        "date": str(am.date),
                        "invoice_date_due": (
                            str(am.invoice_date_due)
                            if getattr(am, "invoice_date_due", None)
                            else None
                        ),
                        "lines": lines,
                    }
                )

            return Response(
                json.dumps({"ok": True, "rows": rows}), content_type="application/json"
            )
        except Exception as e:
            import traceback

            return Response(
                json.dumps(
                    {"ok": False, "error": str(e), "trace": traceback.format_exc()}
                ),
                content_type="application/json",
            )

    @http.route(
        "/api/pos/add", methods=["POST"], type="json", csrf=False, auth="public"
    )
    def pos_add(self, **kwargs):
        data = request.params

        lines = []
        for line in data.get("lines", []):
            lines.append(
                (
                    0,
                    0,
                    {
                        "account_id": line.get("account_id"),
                        "debit": line.get("debit", 0.0),
                        "credit": line.get("credit", 0.0),
                        "name": line.get("name", ""),
                    },
                )
            )

        move_vals = {
            "move_type": "entry",
            "date": data.get("date"),
            "journal_id": data.get("journal_id", 1),
            "line_ids": lines,
        }

        move = request.env["account.move"].sudo().create(move_vals)
        move.action_post()

        return {"result": "Success", "move_id": move.id, "move_name": move.name}

    @http.route(
        "/api/pos/partners",
        methods=["GET"],
        type="http",
        auth="public",
        cors="*",
        csrf=False,
    )
    def get_partners(self, **kwargs):
        """Fetch simplified list of partners for dropdowns."""
        # Optional: restrict to customer_rank > 0 if desired
        partners = (
            request.env["res.partner"].sudo().search_read([], ["id", "display_name"])
        )
        return Response(
            json.dumps({"ok": True, "partners": partners}),
            content_type="application/json",
        )

    @http.route(
        "/api/pos/analytics",
        methods=["GET"],
        type="http",
        auth="public",
        cors="*",
        csrf=False,
    )
    def get_analytics(self, **kwargs):
        """Fetch simplified list of analytic accounts for dropdowns."""
        try:
            # Use direct SQL to bypass project_status_jwt's broken search() override
            # which passes 'count' parameter not supported in Odoo 17
            request.env.cr.execute(
                "SELECT id, name, code FROM account_analytic_account ORDER BY name"
            )
            rows = request.env.cr.dictfetchall()
            analytics = []
            for row in rows:
                analytics.append(
                    {
                        "id": row["id"],
                        "name": str(row["name"]) if row["name"] else "",
                        "code": str(row["code"]) if row["code"] else "",
                    }
                )
            return Response(
                json.dumps({"ok": True, "analytics": analytics}),
                content_type="application/json",
            )
        except Exception as e:
            import traceback

            return Response(
                json.dumps(
                    {"ok": False, "error": str(e), "trace": traceback.format_exc()}
                ),
                content_type="application/json",
            )

    @http.route(
        "/api/pos/projects",
        methods=["GET"],
        type="http",
        auth="public",
        cors="*",
        csrf=False,
    )
    def get_projects(self, **kwargs):
        """Fetch simplified list of projects that have an analytic account for dropdowns."""
        records = request.env["project.project"].sudo().search([])
        projects = []
        for rec in records:
            if rec.analytic_account_id:
                projects.append(
                    {
                        "id": rec.id,
                        "name": rec.name,
                        "analytic_account_id": rec.analytic_account_id.id,
                    }
                )
        return Response(
            json.dumps({"ok": True, "projects": projects}),
            content_type="application/json",
        )

    @http.route(
        "/api/pos/addform", methods=["POST"], type="http", csrf=False, auth="public"
    )
    def pos_add_form(self, **kwargs):
        try:
            date = kwargs.get("date")
            journal_id = int(kwargs.get("journal_id", 1))

            cash_pos_amount = float(kwargs.get("cash_pos_amount", 0.0))
            bank_amount = float(kwargs.get("bank_amount", 0.0))
            tax_amount = float(kwargs.get("tax_amount", 0.0))
            parking_income = float(kwargs.get("parking_income", 0.0))
            # Validate existence of predefined account IDs
            required_account_ids = [513, 514, 716, 824]
            existing_accounts = (
                request.env["account.account"]
                .sudo()
                .search([("id", "in", required_account_ids)])
            )
            existing_account_ids = existing_accounts.mapped("id")

            missing_accounts = [
                acc_id
                for acc_id in required_account_ids
                if acc_id not in existing_account_ids
            ]
            if missing_accounts:
                return Response(
                    json.dumps(
                        {
                            "result": "Error",
                            "error": f"Missing Account ID(s) in Chart of Accounts: {missing_accounts}. The system expects accounts 513, 514, 716, and 824 to exist for recording POS entries.",
                        }
                    ),
                    content_type="application/json",
                )

            lines = [
                (
                    0,
                    0,
                    {
                        "account_id": 513,
                        "debit": cash_pos_amount,
                        "credit": 0.0,
                        "name": "เงินสด @ DT",
                    },
                ),
                (
                    0,
                    0,
                    {
                        "account_id": 514,
                        "debit": bank_amount,
                        "credit": 0.0,
                        "name": "เงินฝากกระแสรายวัน ธ.ไทยพาณิชย์",
                    },
                ),
                (
                    0,
                    0,
                    {
                        "account_id": 716,
                        "debit": 0.0,
                        "credit": tax_amount,
                        "name": "ภาษีขาย",
                    },
                ),
                (
                    0,
                    0,
                    {
                        "account_id": 824,
                        "debit": 0.0,
                        "credit": parking_income,
                        "name": "รายได้ค่าที่จอดรถ",
                    },
                ),
            ]

            move_vals = {
                "move_type": "entry",
                "date": date,
                "journal_id": journal_id,
                "line_ids": lines,
            }

            move = request.env["account.move"].sudo().create(move_vals)
            move.action_post()

            return Response(
                json.dumps(
                    {"result": "Success", "move_id": move.id, "move_name": move.name}
                ),
                content_type="application/json",
            )
        except Exception as e:
            import traceback

            return Response(
                json.dumps(
                    {"ok": False, "error": str(e), "trace": traceback.format_exc()}
                ),
                content_type="application/json",
            )

    # ─── POST from POS machine (Cash + QR) ──────────────────────
    @http.route(
        "/api/pos/addpos", methods=["POST"], type="json", csrf=False, auth="public"
    )
    def pos_add_from_pos(self, **kwargs):
        """
        รับค่า cash + qr จากเครื่อง POS ส่งต่อให้ Model pos.api.service ไปดำเนินการ
        """
        data = request.params
        cash = float(data.get("cash", 0.0))
        qr = float(data.get("qr", 0.0))
        date = data.get("date")
        journal_id = int(data.get("journal_id", 1))
        partner_id = data.get("partner_id")
        analytic_account_id = data.get("analytic_account_id")

        return (
            request.env["pos.api.service"]
            .sudo()
            .create_pos_entry(
                cash, qr, date, journal_id, partner_id, analytic_account_id
            )
        )

    # ─── Validate only (dry-run, no create) ─────────────────────
    @http.route(
        "/api/pos/validate", methods=["POST"], type="json", csrf=False, auth="public"
    )
    def pos_validate(self, **kwargs):
        """
        Dry-run check: ส่งค่า cash + qr ให้ Model ตรวจสอบ
        """
        data = request.params
        cash = float(data.get("cash", 0.0))
        qr = float(data.get("qr", 0.0))
        partner_id = data.get("partner_id")
        analytic_account_id = data.get("analytic_account_id")

        return (
            request.env["pos.api.service"]
            .sudo()
            .validate_pos_entry(cash, qr, partner_id, analytic_account_id)
        )

    @http.route("/pos-monitor", type="http", auth="public", cors="*", csrf=False)
    def pos_monitor(self):
        import os

        # Get the path to the current module directory
        module_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        html_path = os.path.join(module_dir, "static", "pos_monitor.html")

        try:
            with open(html_path, "r", encoding="utf-8") as f:
                content = f.read()
            return Response(content, content_type="text/html; charset=utf-8")
        except FileNotFoundError:
            return request.not_found()
