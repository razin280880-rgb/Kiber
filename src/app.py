"""KIBERone ИгроВАН — веб-приложение пробного урока.

Спринт 1: загрузка готовой игры → мини-лендинг с .sb3 в браузере + QR.
Спринт 2: сессия пробного урока — чекпойнты в реальном времени,
          родительская страница с polling, тест родителя.
"""

from __future__ import annotations

import io
import mimetypes
import os
import secrets
from functools import wraps
from pathlib import Path
from urllib.parse import quote

import qrcode
from dotenv import load_dotenv
from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

from src import storage
from src.ai_writer import generate_report
from src.checkpoints import CHECKPOINTS, CHECKPOINTS_BY_ID, total_count
from src.crm import S20Client
from src.filial_codes import filial_to_code
from src.parent_test import QUESTIONS, QUESTIONS_BY_ID, TRACKS, score_test


load_dotenv()

BASE_URL = os.getenv("BASE_URL", "http://localhost:5000").rstrip("/")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "kiber2026")
DEFAULT_FILIAL = os.getenv("DEFAULT_FILIAL", "Naberezhnye Chelny")
SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_hex(16)

MAX_UPLOAD_MB = 50  # увеличено: .sb3 до 25 + видео до 50
ALLOWED_VIDEO_EXTS = {".mp4", ".mov", ".webm", ".m4v"}
ALLOWED_PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def create_app() -> Flask:
    project_dir = Path(__file__).resolve().parent.parent
    app = Flask(
        __name__,
        template_folder=str(project_dir / "templates"),
        static_folder=str(project_dir / "static"),
    )
    app.secret_key = SECRET_KEY
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024

    # ===============================================================
    #                          Helpers
    # ===============================================================

    def admin_required(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if not session.get("admin"):
                return redirect(url_for("admin_login", next=request.path))
            return view(*args, **kwargs)
        return wrapper

    def make_qr_png(payload: str) -> io.BytesIO:
        img = qrcode.make(payload)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf

    # ===============================================================
    #                          Auth
    # ===============================================================

    @app.route("/")
    def index():
        return redirect(url_for("admin_home"))

    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        if request.method == "POST":
            if request.form.get("password") == ADMIN_PASSWORD:
                session["admin"] = True
                return redirect(request.args.get("next") or url_for("admin_home"))
            flash("Неверный пароль", "error")
        return render_template("admin_login.html")

    @app.route("/admin/logout")
    def admin_logout():
        session.pop("admin", None)
        return redirect(url_for("admin_login"))

    # ===============================================================
    #              Admin home — список сессий + игр
    # ===============================================================

    @app.route("/admin")
    @admin_required
    def admin_home():
        return render_template(
            "admin_home.html",
            sessions=storage.list_sessions(20),
            games=storage.list_games(10),
            default_filial=DEFAULT_FILIAL,
        )

    # ===============================================================
    #          Спринт 1: загрузка игры + публичная страница
    # ===============================================================

    @app.route("/admin/games/upload", methods=["GET", "POST"])
    @admin_required
    def admin_game_upload():
        # Если пришли из сессии — пред-заполнение полей
        session_token = request.args.get("session") or request.form.get("session_token") or ""
        prefilled = None
        if session_token:
            prefilled = storage.load_session(session_token)

        if request.method == "POST":
            child_name = (request.form.get("child_name") or "").strip()
            child_age = (request.form.get("child_age") or "").strip()
            tutor_name = (request.form.get("tutor_name") or "").strip()
            parent_phone = (request.form.get("parent_phone") or "").strip()
            filial = (request.form.get("filial") or DEFAULT_FILIAL).strip()
            sb3_file = request.files.get("sb3")

            errors = []
            if not child_name:
                errors.append("Укажите имя ребёнка")
            try:
                child_age_int = int(child_age)
                if child_age_int < 4 or child_age_int > 18:
                    errors.append("Возраст должен быть от 4 до 18")
            except ValueError:
                errors.append("Возраст должен быть числом")
                child_age_int = 0
            if not tutor_name:
                errors.append("Укажите имя наставника")
            if not sb3_file or not sb3_file.filename:
                errors.append("Загрузите .sb3 файл с игрой")
            elif not sb3_file.filename.lower().endswith(".sb3"):
                errors.append("Файл должен быть .sb3 (Scratch project)")

            if errors:
                for e in errors:
                    flash(e, "error")
                return render_template(
                    "admin_game_upload.html",
                    form=request.form,
                    default_filial=DEFAULT_FILIAL,
                    prefilled=prefilled,
                    session_token=session_token,
                )

            record = storage.save_game(
                child_name=child_name,
                child_age=child_age_int,
                filial=filial,
                tutor_name=tutor_name,
                parent_phone=parent_phone,
                sb3_bytes=sb3_file.read(),
            )
            if session_token:
                storage.attach_game(session_token, record.slug)
            return redirect(url_for("admin_game_share", slug=record.slug))

        return render_template(
            "admin_game_upload.html",
            form={},
            default_filial=DEFAULT_FILIAL,
            prefilled=prefilled,
            session_token=session_token,
        )

    @app.route("/admin/games/<slug>/share")
    @admin_required
    def admin_game_share(slug: str):
        record = storage.load_game(slug)
        if not record:
            abort(404)
        share_url = f"{BASE_URL}/game/{slug}"
        return render_template(
            "admin_game_share.html",
            record=record,
            share_url=share_url,
            qr_url=url_for("game_qr", slug=slug),
        )

    @app.route("/game/<slug>")
    def game_page(slug: str):
        record = storage.load_game(slug)
        if not record:
            abort(404)
        share_url = f"{BASE_URL}/game/{slug}"
        share_text = (
            f"Смотри, {record.child_name} создал(а) свою первую игру "
            f"в KIBERone! Играй прямо в браузере: {share_url}"
        )
        return render_template(
            "game.html",
            record=record,
            sb3_url=url_for("serve_sb3", slug=slug),
            share_url=share_url,
            whatsapp_url=f"https://wa.me/?text={quote(share_text)}",
            telegram_url=f"https://t.me/share/url?url={quote(share_url)}&text={quote(share_text)}",
        )

    @app.route("/game/<slug>.sb3")
    def serve_sb3(slug: str):
        record = storage.load_game(slug)
        if not record or not record.sb3_path.exists():
            abort(404)
        return send_file(
            record.sb3_path,
            mimetype="application/x.scratch.sb3",
            as_attachment=False,
            download_name=f"{slug}.sb3",
        )

    @app.route("/game/<slug>/qr.png")
    def game_qr(slug: str):
        if not storage.load_game(slug):
            abort(404)
        return send_file(make_qr_png(f"{BASE_URL}/game/{slug}"), mimetype="image/png")

    # ===============================================================
    #               Спринт 2: сессии пробного урока
    # ===============================================================

    # Ленивая инициализация — нужна только если CRM настроен.
    _crm_client: dict = {}

    def get_crm() -> S20Client:
        if "client" not in _crm_client:
            _crm_client["client"] = S20Client()
        return _crm_client["client"]

    @app.route("/admin/sessions/lookup")
    @admin_required
    def admin_session_lookup():
        """AJAX endpoint: ищет клиента в CRM по телефону.

        Параметры: phone, filial (опционально, для выбора branch_id).
        Ответ JSON: {found: bool, parent_name, parent_phone, child_name, child_age}
        либо {found: false, reason}.
        """
        phone = (request.args.get("phone") or "").strip()
        filial = (request.args.get("filial") or DEFAULT_FILIAL).strip()
        if not phone:
            return jsonify({"found": False, "reason": "empty_phone"})

        crm = get_crm()
        if crm.dry_run:
            return jsonify({"found": False, "reason": "crm_not_configured"})

        branch_id = crm.branch_id_for_filial(filial)
        if branch_id is None:
            return jsonify({"found": False, "reason": f"no_branch_for_filial:{filial}"})

        result = crm.find_by_phone(branch_id, phone)
        if not result:
            return jsonify({"found": False, "reason": "not_found"})

        return jsonify({"found": True, **result})

    @app.route("/admin/sessions/new", methods=["GET", "POST"])
    @admin_required
    def admin_session_new():
        if request.method == "POST":
            child_name = (request.form.get("child_name") or "").strip()
            child_age = (request.form.get("child_age") or "").strip()
            tutor_name = (request.form.get("tutor_name") or "").strip()
            parent_name = (request.form.get("parent_name") or "").strip()
            parent_phone = (request.form.get("parent_phone") or "").strip()
            filial = (request.form.get("filial") or DEFAULT_FILIAL).strip()

            errors = []
            if not child_name:
                errors.append("Укажите имя ребёнка")
            try:
                child_age_int = int(child_age)
                if child_age_int < 4 or child_age_int > 18:
                    errors.append("Возраст должен быть от 4 до 18")
            except ValueError:
                errors.append("Возраст должен быть числом")
                child_age_int = 0
            if not tutor_name:
                errors.append("Укажите имя наставника")
            if not parent_name:
                errors.append("Укажите имя родителя (как обратиться)")

            if errors:
                for e in errors:
                    flash(e, "error")
                return render_template(
                    "admin_session_new.html",
                    form=request.form,
                    default_filial=DEFAULT_FILIAL,
                    crm_enabled=not get_crm().dry_run,
                )

            sess = storage.create_session(
                child_name=child_name,
                child_age=child_age_int,
                filial=filial,
                tutor_name=tutor_name,
                parent_phone=parent_phone,
                parent_name=parent_name,
            )
            return redirect(url_for("admin_session_view", token=sess.token))

        return render_template(
            "admin_session_new.html",
            form={},
            default_filial=DEFAULT_FILIAL,
            crm_enabled=not get_crm().dry_run,
        )

    @app.route("/admin/sessions/<token>")
    @admin_required
    def admin_session_view(token: str):
        sess = storage.load_session(token)
        if not sess:
            abort(404)
        parent_url = f"{BASE_URL}/parent/{token}"
        return render_template(
            "admin_session.html",
            session=sess,
            checkpoints=CHECKPOINTS,
            done_ids=sess.checkpoint_ids,
            total=total_count(),
            parent_url=parent_url,
            qr_url=url_for("admin_session_qr", token=token),
        )

    @app.route("/admin/sessions/<token>/qr.png")
    @admin_required
    def admin_session_qr(token: str):
        """QR для родителя на текущем уроке — ведёт на live-страницу /parent."""
        if not storage.load_session(token):
            abort(404)
        return send_file(make_qr_png(f"{BASE_URL}/parent/{token}"), mimetype="image/png")

    @app.route("/admin/sessions/<token>/profile-qr.png")
    @admin_required
    def admin_session_profile_qr(token: str):
        """QR для паспорта разработчика — ведёт на постоянный /dev профиль."""
        if not storage.load_session(token):
            abort(404)
        return send_file(make_qr_png(f"{BASE_URL}/dev/{token}"), mimetype="image/png")

    @app.route("/admin/sessions/<token>/checkpoint/<cp_id>", methods=["POST"])
    @admin_required
    def admin_session_checkpoint(token: str, cp_id: str):
        if cp_id not in CHECKPOINTS_BY_ID:
            abort(400)
        action = request.form.get("action", "add")
        note = (request.form.get("note") or "").strip()
        if action == "remove":
            storage.remove_checkpoint(token, cp_id)
        else:
            storage.add_checkpoint(token, cp_id, note)
        return redirect(url_for("admin_session_view", token=token))

    @app.route("/admin/sessions/<token>/upload-video", methods=["POST"])
    @admin_required
    def admin_session_upload_video(token: str):
        sess = storage.load_session(token)
        if not sess:
            abort(404)
        video_file = request.files.get("video")
        if not video_file or not video_file.filename:
            flash("Файл не выбран", "error")
            return redirect(url_for("admin_session_view", token=token))
        ext = Path(video_file.filename).suffix.lower()
        if ext not in ALLOWED_VIDEO_EXTS:
            flash(f"Поддерживаются форматы: {', '.join(sorted(ALLOWED_VIDEO_EXTS))}", "error")
            return redirect(url_for("admin_session_view", token=token))
        storage.VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"{token}{ext}"
        target = storage.VIDEOS_DIR / filename
        video_file.save(str(target))
        storage.attach_video(token, filename)
        flash("Видео-нарезка загружена. Через 1 час после завершения урока отправится родителю.", "success")
        return redirect(url_for("admin_session_view", token=token))

    @app.route("/admin/sessions/<token>/finish", methods=["POST"])
    @admin_required
    def admin_session_finish(token: str):
        if not storage.load_session(token):
            abort(404)
        storage.finish_session(token)
        flash("Урок завершён. Можешь загрузить игру ребёнка.", "success")
        return redirect(url_for("admin_session_view", token=token))

    # ---- Паспорт разработчика (Спринт 4) ---------------------

    @app.route("/admin/sessions/<token>/passport/issue", methods=["POST"])
    @admin_required
    def admin_passport_issue(token: str):
        sess = storage.load_session(token)
        if not sess:
            abort(404)
        code = filial_to_code(sess.filial)
        storage.issue_passport(token, code)
        flash("Паспорт выдан. Можно распечатать или загрузить фото ребёнка.", "success")
        return redirect(url_for("admin_session_view", token=token))

    @app.route("/admin/sessions/<token>/passport/photo", methods=["POST"])
    @admin_required
    def admin_passport_photo(token: str):
        sess = storage.load_session(token)
        if not sess:
            abort(404)
        photo_file = request.files.get("photo")
        if not photo_file or not photo_file.filename:
            flash("Файл не выбран", "error")
            return redirect(url_for("admin_session_view", token=token))
        ext = Path(photo_file.filename).suffix.lower()
        if ext not in ALLOWED_PHOTO_EXTS:
            flash(f"Поддерживаются: {', '.join(sorted(ALLOWED_PHOTO_EXTS))}", "error")
            return redirect(url_for("admin_session_view", token=token))
        storage.PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"{token}{ext}"
        target = storage.PHOTOS_DIR / filename
        photo_file.save(str(target))
        storage.attach_passport_photo(token, filename)
        flash("Фото загружено", "success")
        return redirect(url_for("admin_session_view", token=token))

    @app.route("/admin/sessions/<token>/passport/photo.<ext>")
    @admin_required
    def admin_passport_photo_serve(token: str, ext: str):
        sess = storage.load_session(token)
        if not sess or not sess.passport_photo:
            abort(404)
        path = storage.PHOTOS_DIR / sess.passport_photo
        if not path.exists():
            abort(404)
        mime, _ = mimetypes.guess_type(sess.passport_photo)
        return send_file(path, mimetype=mime or "image/jpeg")

    @app.route("/admin/sessions/<token>/passport")
    @admin_required
    def admin_passport_view(token: str):
        sess = storage.load_session(token)
        if not sess:
            abort(404)
        if not sess.passport_serial:
            flash("Сначала выдай паспорт (кнопка «Выдать паспорт»).", "error")
            return redirect(url_for("admin_session_view", token=token))
        track = None
        if sess.parent_test and sess.parent_test.get("result_key") in TRACKS:
            track = TRACKS[sess.parent_test["result_key"]]
        photo_url = None
        if sess.passport_photo:
            photo_url = url_for(
                "admin_passport_photo_serve",
                token=token,
                ext=sess.passport_photo.rsplit(".", 1)[-1],
            )
        profile_url = f"{BASE_URL}/dev/{token}"
        return render_template(
            "passport.html",
            session=sess,
            track=track,
            photo_url=photo_url,
            parent_url=profile_url,
            qr_url=url_for("admin_session_profile_qr", token=token),
        )

    @app.route("/admin/sessions/<token>/generate-report", methods=["POST"])
    @admin_required
    def admin_session_generate_report(token: str):
        sess = storage.load_session(token)
        if not sess:
            abort(404)
        try:
            checkpoints_payload = []
            for ev in sess.checkpoints:
                cp = CHECKPOINTS_BY_ID.get(ev.id)
                if cp:
                    checkpoints_payload.append({
                        "id": cp.id,
                        "emoji": cp.emoji,
                        "title_admin": cp.title_admin,
                        "parent_message": cp.parent_message,
                        "timestamp": ev.timestamp,
                        "note": ev.note,
                    })
            report = generate_report(
                child_name=sess.child_name,
                child_age=sess.child_age,
                grade=sess.grade,
                parent_name=sess.parent_name,
                tutor_name=sess.tutor_name,
                filial=sess.filial,
                checkpoints=checkpoints_payload,
                parent_test=sess.parent_test,
            )
            storage.save_report(token, report)
            flash("Отчёт сгенерирован. Worker отправит родителю через 24ч либо вручную нажми «Открыть отчёт».", "success")
        except Exception as e:
            flash(f"Ошибка генерации: {e}", "error")
        return redirect(url_for("admin_session_view", token=token))

    # ===============================================================
    #                Спринт 2: страницы родителя
    # ===============================================================

    @app.route("/parent/<token>")
    def parent_page(token: str):
        sess = storage.load_session(token)
        if not sess:
            abort(404)
        return render_template(
            "parent.html",
            session=sess,
            checkpoints=CHECKPOINTS,
            done_ids=sess.checkpoint_ids,
            total=total_count(),
        )

    # ---- Профиль разработчика (публичный) --------------------

    @app.route("/dev/<token>")
    def dev_profile(token: str):
        """Публичный профиль ребёнка-разработчика.

        Куда ведёт QR с паспорта разработчика. После завершения пробного
        здесь живёт всё «портфолио» ребёнка: имя, грейд, трек, игры,
        достижения. Виральная страница для шеринга.
        """
        sess = storage.load_session(token)
        if not sess:
            abort(404)
        game = storage.load_game(sess.game_slug) if sess.game_slug else None
        track = None
        if sess.parent_test and sess.parent_test.get("result_key") in TRACKS:
            track = TRACKS[sess.parent_test["result_key"]]
        profile_url = f"{BASE_URL}/dev/{token}"
        share_text = (
            f"Смотри портфолио {sess.child_name} — Junior {sess.grade} "
            f"в KIBERone! {profile_url}"
        )
        return render_template(
            "dev_profile.html",
            session=sess,
            game=game,
            track=track,
            profile_url=profile_url,
            whatsapp_url=f"https://wa.me/?text={quote(share_text)}",
            telegram_url=f"https://t.me/share/url?url={quote(profile_url)}&text={quote(share_text)}",
        )

    @app.route("/parent/<token>/status.json")
    def parent_status(token: str):
        sess = storage.load_session(token)
        if not sess:
            return jsonify({"error": "not_found"}), 404
        done_ids = list(sess.checkpoint_ids)
        latest = sess.checkpoints[-1] if sess.checkpoints else None
        return jsonify({
            "child_name": sess.child_name,
            "grade": sess.grade,
            "finished": sess.is_finished,
            "done_count": len(done_ids),
            "total_count": total_count(),
            "done_ids": done_ids,
            "latest_id": latest.id if latest else None,
            "latest_at": latest.timestamp if latest else None,
            "test_done": sess.parent_test is not None,
            "game_slug": sess.game_slug,
            "report_ready": sess.report_data is not None,
        })

    @app.route("/parent/<token>/test", methods=["GET", "POST"])
    def parent_test(token: str):
        sess = storage.load_session(token)
        if not sess:
            abort(404)

        if request.method == "POST":
            answers: dict[str, str] = {}
            missing = []
            for q in QUESTIONS:
                ans = request.form.get(q.id)
                if not ans:
                    missing.append(q.id)
                else:
                    answers[q.id] = ans
            if missing:
                flash("Пожалуйста, ответьте на все вопросы", "error")
                return render_template(
                    "parent_test.html",
                    session=sess,
                    questions=QUESTIONS,
                    answers=answers,
                )
            winner, _scores = score_test(answers)
            track = TRACKS[winner]
            storage.save_parent_test(token, answers, winner, track.label)
            return redirect(url_for("parent_result", token=token))

        return render_template(
            "parent_test.html",
            session=sess,
            questions=QUESTIONS,
            answers=(sess.parent_test or {}).get("answers", {}),
        )

    @app.route("/parent/<token>/report")
    def parent_report(token: str):
        sess = storage.load_session(token)
        if not sess:
            abort(404)
        if not sess.report_data:
            # Отчёт ещё не сгенерирован
            return render_template("report_pending.html", session=sess), 202
        track = None
        if sess.parent_test and sess.parent_test.get("result_key") in TRACKS:
            track = TRACKS[sess.parent_test["result_key"]]
        return render_template(
            "report.html",
            session=sess,
            report=sess.report_data,
            track=track,
        )

    @app.route("/parent/<token>/video")
    def parent_video(token: str):
        sess = storage.load_session(token)
        if not sess or not sess.video_filename:
            abort(404)
        path = storage.VIDEOS_DIR / sess.video_filename
        if not path.exists():
            abort(404)
        mime, _ = mimetypes.guess_type(sess.video_filename)
        return send_file(path, mimetype=mime or "video/mp4")

    @app.route("/parent/<token>/result")
    def parent_result(token: str):
        sess = storage.load_session(token)
        if not sess:
            abort(404)
        if not sess.parent_test:
            return redirect(url_for("parent_test", token=token))
        track = TRACKS[sess.parent_test["result_key"]]
        return render_template(
            "parent_result.html",
            session=sess,
            track=track,
        )

    # ===============================================================
    #                          Errors
    # ===============================================================

    @app.errorhandler(413)
    def too_large(_):
        flash(f"Файл слишком большой (макс {MAX_UPLOAD_MB} МБ)", "error")
        return redirect(request.referrer or url_for("admin_home"))

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
