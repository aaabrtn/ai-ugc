"""Server-side polling for in-progress KIE video generations.

Without this, a generation only ever advances from waiting/queuing/generating
to success/fail when a browser happens to call GET /video-status — which only
happens while someone has the app open. Close the tab, or navigate away for
long enough, and the row (and the credits already spent on it) just sits
stuck mid-flight forever, even though KIE finished the job on its own servers
minutes ago. This background thread polls every in-progress generation on a
fixed interval regardless of whether anyone is looking at the app at all, so
History reliably fills in on its own.
"""

import logging
import threading
import time

from app.database import SessionLocal
from app.integrations.kie import KieError, KieNotConfigured
from app.models import Generation, VideoStatus

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 20
IN_PROGRESS_STATUSES = (VideoStatus.waiting, VideoStatus.queuing, VideoStatus.generating)


def _poll_once() -> None:
    from app.routers.generations import refresh_video_status  # local import avoids a circular import at startup

    db = SessionLocal()
    try:
        rows = db.query(Generation).filter(Generation.video_status.in_(IN_PROGRESS_STATUSES)).all()
        for g in rows:
            try:
                refresh_video_status(db, g)
            except (KieNotConfigured, KieError) as e:
                logger.warning("Background poll: KIE check failed for generation %s: %s", g.id, e)
            except Exception:
                logger.exception("Background poll: unexpected error checking generation %s", g.id)
    finally:
        db.close()


def _poll_loop() -> None:
    while True:
        try:
            _poll_once()
        except Exception:
            logger.exception("Background poll: loop iteration failed")
        time.sleep(POLL_INTERVAL_SECONDS)


def start_video_status_poller() -> None:
    thread = threading.Thread(target=_poll_loop, name="video-status-poller", daemon=True)
    thread.start()
