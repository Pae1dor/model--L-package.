from odoo import models, api


class PosApiService(models.AbstractModel):
    _name = "pos.api.service"
    _description = "POS API Business Logic Service"

    @api.model
    def _calc_vat_service(self, total_credit):
        """
        สูตรคำนวณ:
          VAT        = total_credit × 7 / 107
          ค่าบริการ  = total_credit × 100 / 107
        ปรับ rounding ให้ vat + service == total_credit เสมอ
        """
        vat = round(total_credit * 7 / 107, 2)
        service = round(total_credit - vat, 2)  # ensure exact balance
        return vat, service

    @api.model
    def _create_line(self, account_id, debit, credit, name, analytic_account_id=None):
        """
        สร้างข้อมูลสำหรับ account.move.line
        """
        analytic_distribution = False
        if analytic_account_id:
            analytic_distribution = {str(analytic_account_id): 100}

        line_vals = {
            "account_id": account_id,
            "debit": debit,
            "credit": credit,
            "name": name,
        }

        if analytic_distribution:
            line_vals["analytic_distribution"] = analytic_distribution

        return line_vals

    @api.model
    def _create_head(self, date, journal_id, partner_id, lines):
        """
        สร้าง account.move (Header)
        """
        move_vals = {
            "move_type": "entry",
            "date": date,
            "journal_id": journal_id,
            "line_ids": [(0, 0, ld) for ld in lines],
        }
        if partner_id:
            move_vals["partner_id"] = int(partner_id)

        return move_vals

    @api.model
    def create_pos_entry(
        self, cash, qr, date, journal_id, partner_id=None, analytic_account_id=None
    ):
        """
        สร้าง Journal Entry จาก Cash + QR
        """
        if cash <= 0 and qr <= 0:
            return {
                "ok": False,
                "error": "cash and qr must be positive numbers, at least one > 0",
            }

        if partner_id:
            try:
                partner_id = int(partner_id)
                partner = (
                    self.env["res.partner"].sudo().search([("id", "=", partner_id)])
                )
                if not partner:
                    return {
                        "ok": False,
                        "error": f"Invalid partner_id: Record does not exist in res.partner ({partner_id})",
                    }
            except ValueError:
                return {"ok": False, "error": "partner_id must be an integer"}

        if analytic_account_id:
            try:
                analytic_account_id = int(analytic_account_id)
                # Use browse + exists to bypass broken search() override in project_status_jwt
                analytic = (
                    self.env["account.analytic.account"]
                    .sudo()
                    .browse(analytic_account_id)
                    .exists()
                )
                if not analytic:
                    return {
                        "ok": False,
                        "error": f"Invalid analytic_account_id: Record does not exist in account.analytic.account ({analytic_account_id})",
                    }
            except ValueError:
                return {"ok": False, "error": "analytic_account_id must be an integer"}

        required_account_ids = [513, 514, 824, 716]
        existing_accounts = (
            self.env["account.account"]
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
            return {
                "ok": False,
                "error": f"Missing Account ID(s) in Chart of Accounts: {missing_accounts}. The system expects accounts 513, 514, 716, and 824.",
            }

        total_credit = round(cash + qr, 2)
        vat, service = self._calc_vat_service(total_credit)

        line_defs = [
            self._create_line(513, cash, 0.0, "เงินสดPOS", analytic_account_id),
            self._create_line(
                514, qr, 0.0, "เงินฝากกระแสรายวัน ธ.ไทยพาณิชย์", analytic_account_id
            ),
            self._create_line(824, 0.0, service, "รายได้ค่าที่จอดรถ", analytic_account_id),
            self._create_line(716, 0.0, vat, "ภาษีขาย", analytic_account_id),
        ]

        sum_debit = round(sum(l["debit"] for l in line_defs), 2)
        sum_credit = round(sum(l["credit"] for l in line_defs), 2)

        if sum_debit != sum_credit:
            return {
                "ok": False,
                "error": f"Balance check failed: ΣDebit ({sum_debit}) ≠ ΣCredit ({sum_credit})",
                "sum_debit": sum_debit,
                "sum_credit": sum_credit,
            }

        move_vals = self._create_head(date, journal_id, partner_id, line_defs)
        move = self.env["account.move"].sudo().create(move_vals)
        move.action_post()

        return {
            "ok": True,
            "result": "Success",
            "move_id": move.id,
            "move_name": move.name,
            "validation": {
                "cash": cash,
                "qr": qr,
                "total_credit": total_credit,
                "vat": vat,
                "service": service,
                "sum_debit": sum_debit,
                "sum_credit": sum_credit,
                "balanced": True,
                "partner_id": partner_id,
                "analytic_account_id": analytic_account_id,
            },
            "lines": [
                {"account": "11010102 เงินสดPOS", "dr": cash, "cr": 0.0},
                {
                    "account": "11010201 เงินฝากกระแสรายวัน ธ.ไทยพาณิชย์",
                    "dr": qr,
                    "cr": 0.0,
                },
                {"account": "41020201 รายได้ค่าที่จอดรถ", "dr": 0.0, "cr": service},
                {"account": "21060500 ภาษีขาย", "dr": 0.0, "cr": vat},
            ],
        }

    @api.model
    def validate_pos_entry(self, cash, qr, partner_id=None, analytic_account_id=None):
        """
        Dry-run validation
        """
        total_credit = round(cash + qr, 2)
        vat, service = self._calc_vat_service(total_credit)

        sum_debit = round(cash + qr, 2)
        sum_credit = round(vat + service, 2)
        balanced = sum_debit == sum_credit

        return {
            "ok": True,
            "validation": {
                "cash": cash,
                "qr": qr,
                "total_credit": total_credit,
                "vat_formula": "ΣCredit × 7 / 107",
                "vat": vat,
                "service_formula": "ΣCredit × 100 / 107",
                "service": service,
                "sum_debit": sum_debit,
                "sum_credit": sum_credit,
                "balanced": balanced,
                "partner_id": partner_id,
                "analytic_account_id": analytic_account_id,
            },
            "lines": [
                {"account": "11010102 เงินสดPOS", "dr": cash, "cr": 0.0},
                {
                    "account": "11010201 เงินฝากกระแสรายวัน ธ.ไทยพาณิชย์",
                    "dr": qr,
                    "cr": 0.0,
                },
                {"account": "41020201 รายได้ค่าที่จอดรถ", "dr": 0.0, "cr": service},
                {"account": "21060500 ภาษีขาย", "dr": 0.0, "cr": vat},
            ],
        }
