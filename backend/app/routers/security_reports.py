"""Where browsers send Content-Security-Policy violation reports (findings F25).

Anyone may post here, signed in or not, because the browser sends these on its own. The
route changes nothing: it only writes one cleaned log line per report, so we can see when
the policy blocks something the app needs, or when someone tries to inject a script.
"""

import logging

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.security import CSP_REPORT_PATH, parse_csp_reports

router = APIRouter(tags=["security"])
logger = logging.getLogger("app.security.csp")


@router.post(CSP_REPORT_PATH, status_code=status.HTTP_204_NO_CONTENT)
async def csp_report(request: Request) -> Response:
    reports = parse_csp_reports(await request.body(), request.headers.get("content-type", ""))
    if reports is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Not a CSP report")
    for report in reports:
        logger.warning(
            "CSP violation: directive=%s blocked=%s page=%s",
            report["directive"],
            report["blocked"],
            report["page"],
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
