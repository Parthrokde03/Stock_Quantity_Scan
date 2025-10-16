# -*- coding: utf-8 -*-
import json
import logging
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

def _parse_code_qty(raw):
    raw = (raw or "").strip()
    if not raw:
        return "", None
    base = raw.split("/", 1)[0]
    qty = None
    if "/" in raw:
        tail = raw.split("/", 1)[1]
        tail = tail.split("/", 1)[0]
        try:
            qty = float(tail)
        except Exception:
            qty = None
    return base, qty

def _consume_quant(code, token, product_tmpl_id=None):
    # --- 0) auth ---
    sys_token = (request.env["ir.config_parameter"].sudo()
                 .get_param("stock_quantity_scan.scan_token", "") or "")
    sys_token = sys_token.strip()
    token = (token or "").strip()

    if not sys_token or not token or token != sys_token:
        # TEMP: log what we see (will appear in odoo log)
        _logger.warning("scan unauthorized: got token=%r, sys_token=%r", token, sys_token)
        return {"ok": False, "error": "unauthorized"}

    # --- 1) parse ---
    base_code, qty = _parse_code_qty(code)
    if not base_code:
        return {"ok": False, "error": "missing_code"}

    Quant = request.env["stock.quant"].sudo()

    # --- 2) find quant ---
    domain_bar = [("scan_barcode", "=", base_code), ("quantity", ">", 0)]
    domain_lot = [("lot_id.name", "=", base_code), ("quantity", ">", 0)]
    if product_tmpl_id:
        try:
            ptid = int(product_tmpl_id)
            domain_bar.append(("product_id.product_tmpl_id", "=", ptid))
            domain_lot.append(("product_id.product_tmpl_id", "=", ptid))
        except Exception:
            pass

    quant = Quant.search(domain_bar, limit=1) or Quant.search(domain_lot, limit=1)
    if not quant:
        return {"ok": False, "error": "not_found", "scanned": code}

    # --- 3) consume ---
    try:
        # send a cleaned code to the model (no /220/60)
        code_clean = f"{base_code}/{qty}" if qty is not None else base_code
        new_qty = quant.action_consume_by_code(code_clean, qty=qty)
    except Exception as e:
        return {"ok": False, "error": "consume_failed", "details": str(e), "scanned": code}

    removed = False
    try:
        quant.invalidate_cache(["quantity"])
        if not quant.quantity or quant.quantity <= 0:
            quant.unlink()
            removed = True
    except Exception:
        pass

    return {
        "ok": True,
        "quant_id": quant.id if quant and not removed else None,
        # "removed": removed,
        "new_qty": 0.0 if removed else new_qty,
        "scanned": code,
    }

class StockQuantScanController(http.Controller):

    @http.route("/stock_quantity_scan/scan", auth="public", methods=["GET"], csrf=False, type="http")
    def scan_get(self, **kw):
        res = _consume_quant(
            code=kw.get("code"),
            token=kw.get("token"),
            product_tmpl_id=kw.get("product_tmpl_id"),
        )
        return request.make_response(
            json.dumps(res),
            headers=[("Content-Type", "application/json; charset=utf-8")],
        )

    @http.route("/stock_quantity_scan/scan_json", auth="public", methods=["POST"], csrf=False, type="json")
    def scan_json(self, code=None, token=None, product_tmpl_id=None):
        return _consume_quant(code=code, token=token, product_tmpl_id=product_tmpl_id)

    # --- TEMPORARY DEBUG ROUTE: remove after testing ---
    @http.route("/stock_quantity_scan/_debug_token", auth="user", type="json", methods=["POST"], csrf=False)
    def debug_token(self, token=None):
        sys_token = (request.env["ir.config_parameter"].sudo()
                     .get_param("stock_quantity_scan.scan_token", "") or "").strip()
        return {
            "given_token": (token or "").strip(),
            "system_token": sys_token,
            "equal": ((token or "").strip() == sys_token),
        }
