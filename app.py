import os
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import LoginManager, UserMixin, current_user, login_required, login_user, logout_user
from flask_sqlalchemy import SQLAlchemy
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import func
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from config import Config

app = Flask(__name__)
app.config.from_object(Config)
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

room_services = db.Table("room_services", db.Column("room_id", db.Integer, db.ForeignKey("rooms.id"), primary_key=True), db.Column("service_id", db.Integer, db.ForeignKey("services.id"), primary_key=True))

class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="tenant")
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=True)
    tenant = db.relationship("Tenant", foreign_keys=[tenant_id])

class Room(db.Model):
    __tablename__ = "rooms"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(30), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    rent = db.Column(db.Numeric(12, 2), nullable=False)
    area = db.Column(db.Numeric(8, 2))
    max_occupants = db.Column(db.Integer, default=1)
    status = db.Column(db.String(20), default="vacant")
    notes = db.Column(db.Text)
    tenants = db.relationship("Tenant", backref="room", lazy=True)
    services = db.relationship("Service", secondary=room_services, lazy="subquery")

class Tenant(db.Model):
    __tablename__ = "tenants"
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20)); cccd = db.Column(db.String(30), unique=True)
    birth_date = db.Column(db.Date); gender = db.Column(db.String(15)); permanent_address = db.Column(db.Text)
    move_in_date = db.Column(db.Date); room_id = db.Column(db.Integer, db.ForeignKey("rooms.id"))
    deposit = db.Column(db.Numeric(12, 2), default=0); notes = db.Column(db.Text)
    id_front = db.Column(db.String(255)); id_back = db.Column(db.String(255)); contract_file = db.Column(db.String(255))

class UtilityReading(db.Model):
    __tablename__ = "utility_readings"
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey("rooms.id"), nullable=False); room = db.relationship("Room")
    reading_month = db.Column(db.Date, nullable=False)
    old_electricity = db.Column(db.Numeric(12,2), nullable=False); new_electricity = db.Column(db.Numeric(12,2), nullable=False); electricity_rate = db.Column(db.Numeric(12,2), nullable=False)
    old_water = db.Column(db.Numeric(12,2), nullable=False); new_water = db.Column(db.Numeric(12,2), nullable=False); water_rate = db.Column(db.Numeric(12,2), nullable=False)
    __table_args__ = (db.UniqueConstraint("room_id", "reading_month"),)
    @property
    def electricity_fee(self): return (self.new_electricity - self.old_electricity) * self.electricity_rate
    @property
    def water_fee(self): return (self.new_water - self.old_water) * self.water_rate

class Service(db.Model):
    __tablename__ = "services"
    id = db.Column(db.Integer, primary_key=True); name = db.Column(db.String(100), unique=True, nullable=False)
    unit_price = db.Column(db.Numeric(12,2), nullable=False); calculation = db.Column(db.String(10), default="room"); is_active = db.Column(db.Boolean, default=True)

class Invoice(db.Model):
    __tablename__ = "invoices"
    id = db.Column(db.Integer, primary_key=True); code = db.Column(db.String(40), unique=True, nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey("rooms.id"), nullable=False); room = db.relationship("Room")
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id")); tenant = db.relationship("Tenant")
    invoice_month = db.Column(db.Date, nullable=False); room_fee = db.Column(db.Numeric(12,2), default=0); electricity_fee = db.Column(db.Numeric(12,2), default=0); water_fee = db.Column(db.Numeric(12,2), default=0); service_fee = db.Column(db.Numeric(12,2), default=0); extra_fee = db.Column(db.Numeric(12,2), default=0); discount = db.Column(db.Numeric(12,2), default=0); total = db.Column(db.Numeric(12,2), default=0)
    due_date = db.Column(db.Date); status = db.Column(db.String(20), default="unpaid"); notes = db.Column(db.Text)
    payments = db.relationship("Payment", backref="invoice", cascade="all, delete-orphan")
    payment_requests = db.relationship("PaymentRequest", backref="invoice", cascade="all, delete-orphan")
    details = db.relationship("InvoiceDetail", backref="invoice", cascade="all, delete-orphan")
    @property
    def paid_amount(self): return sum((p.amount for p in self.payments), Decimal("0"))
    @property
    def balance(self): return self.total - self.paid_amount
    @property
    def pending_payment_request(self):
        return next((item for item in self.payment_requests if item.status == "pending"), None)

class Payment(db.Model):
    __tablename__ = "payments"
    id = db.Column(db.Integer, primary_key=True); invoice_id = db.Column(db.Integer, db.ForeignKey("invoices.id"), nullable=False)
    amount = db.Column(db.Numeric(12,2), nullable=False); paid_at = db.Column(db.DateTime, default=datetime.now); method = db.Column(db.String(50)); notes = db.Column(db.Text)

class PaymentRequest(db.Model):
    __tablename__ = "payment_requests"
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoices.id"), nullable=False)
    requester_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    amount = db.Column(db.Numeric(12,2), nullable=False)
    method = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending")
    requested_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    processed_at = db.Column(db.DateTime)

class InvoiceDetail(db.Model):
    __tablename__ = "invoice_details"
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoices.id"), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    amount = db.Column(db.Numeric(12,2), nullable=False)

@login_manager.user_loader
def load_user(uid): return db.session.get(User, int(uid))

@app.before_request
def restrict_tenant_access():
    if not current_user.is_authenticated or current_user.role != "tenant": return
    allowed = {"logout", "invoices", "request_invoice_payment", "print_invoice", "pdf", "static"}
    if request.endpoint not in allowed: abort(403)

def money(field):
    try: return Decimal(request.form.get(field, "0") or "0")
    except: return Decimal("0")
def month(field): return datetime.strptime(request.form[field], "%Y-%m").date().replace(day=1)
def selected_service_details(room):
    service_ids = [int(value) for value in request.form.getlist("service_ids")]
    services = Service.query.filter(Service.id.in_(service_ids), Service.is_active == True).all() if service_ids else []
    people = max(1, len(room.tenants))
    return [(service, service.unit_price * (people if service.calculation == "person" else 1)) for service in services]
def state(v): return {"vacant":"Trống", "occupied":"Đang thuê", "maintenance":"Sửa chữa", "unpaid":"Chưa thanh toán", "partial":"Thanh toán một phần", "pending":"Đang xử lý", "paid":"Đã thanh toán", "rejected":"Đã từ chối"}.get(v,v)
app.jinja_env.globals.update(state=state, today=date.today)

@app.route("/login", methods=["GET","POST"])
def login():
    if current_user.is_authenticated: return redirect(url_for("dashboard"))
    if request.method == "POST":
        user=User.query.filter_by(username=request.form.get("username")).first()
        if user and check_password_hash(user.password_hash,request.form.get("password","")):
            login_user(user); return redirect(url_for("invoices" if user.role == "tenant" else "dashboard"))
        flash("Sai tên đăng nhập hoặc mật khẩu.","danger")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user(); return redirect(url_for("login"))

@app.route("/accounts", methods=["GET", "POST"])
@login_required
def accounts():
    if current_user.role != "admin": abort(403)
    if request.method == "POST":
        try:
            tenant = db.session.get(Tenant, int(request.form["tenant_id"]))
            if not tenant: raise ValueError()
            if User.query.filter_by(tenant_id=tenant.id).first():
                flash("Người thuê này đã có tài khoản.", "danger")
            else:
                db.session.add(User(username=request.form["username"], full_name=tenant.full_name, password_hash=generate_password_hash(request.form["password"]), role="tenant", tenant_id=tenant.id))
                db.session.commit(); flash("Đã tạo tài khoản người thuê.", "success")
        except Exception:
            db.session.rollback(); flash("Không thể tạo tài khoản. Tên đăng nhập có thể đã tồn tại.", "danger")
        return redirect(url_for("accounts"))
    return render_template("accounts.html", accounts=User.query.filter_by(role="tenant").order_by(User.username).all(), tenants=Tenant.query.order_by(Tenant.full_name).all())

@app.route("/accounts/<int:id>/delete", methods=["POST"])
@login_required
def delete_account(id):
    if current_user.role != "admin": abort(403)
    account = db.get_or_404(User, id)
    if account.role == "admin": abort(403)
    db.session.delete(account); db.session.commit(); flash("Đã xóa tài khoản người thuê.", "success")
    return redirect(url_for("accounts"))

@app.route("/")
@login_required
def dashboard():
    first=date.today().replace(day=1)
    revenue=db.session.query(func.coalesce(func.sum(Payment.amount),0)).join(Invoice).filter(Invoice.invoice_month==first).scalar()
    return render_template("dashboard.html",total_rooms=Room.query.count(),occupied=Room.query.filter_by(status="occupied").count(),vacant=Room.query.filter_by(status="vacant").count(),unpaid=Invoice.query.filter(Invoice.status!="paid").count(),revenue=revenue,debts=Invoice.query.filter(Invoice.status!="paid").order_by(Invoice.due_date).all())

@app.route("/rooms",methods=["GET","POST"])
@login_required
def rooms():
    if request.method=="POST":
        try:
            db.session.add(Room(code=request.form["code"],name=request.form["name"],rent=money("rent"),area=money("area") if request.form.get("area") else None,max_occupants=int(request.form.get("max_occupants",1)),status=request.form["status"],notes=request.form.get("notes"))); db.session.commit(); flash("Đã thêm phòng.","success")
        except Exception: db.session.rollback(); flash("Mã phòng đã tồn tại hoặc dữ liệu không hợp lệ.","danger")
        return redirect(url_for("rooms"))
    q=request.args.get("q",""); st=request.args.get("status",""); data=Room.query
    if q: data=data.filter((Room.code.contains(q))|(Room.name.contains(q)))
    if st: data=data.filter_by(status=st)
    return render_template("rooms.html",rooms=data.order_by(Room.code).all())

@app.route("/rooms/<int:id>/delete",methods=["POST"])
@login_required
def delete_room(id):
    room=db.get_or_404(Room,id)
    if room.tenants: flash("Không thể xóa phòng còn người thuê.","danger")
    else: db.session.delete(room); db.session.commit(); flash("Đã xóa phòng.","success")
    return redirect(url_for("rooms"))

@app.route("/rooms/<int:id>/update", methods=["POST"])
@login_required
def update_room(id):
    room = db.get_or_404(Room, id)
    try:
        room.code = request.form["code"]; room.name = request.form["name"]; room.rent = money("rent")
        room.area = money("area") if request.form.get("area") else None
        room.max_occupants = int(request.form.get("max_occupants", 1)); room.status = request.form["status"]
        room.notes = request.form.get("notes"); db.session.commit(); flash("Đã cập nhật phòng.", "success")
    except Exception:
        db.session.rollback(); flash("Mã phòng đã tồn tại hoặc dữ liệu không hợp lệ.", "danger")
    return redirect(url_for("rooms"))

def upload(field):
    f=request.files.get(field)
    if not f or not f.filename:return None
    name=f"{datetime.now():%Y%m%d%H%M%S%f}_{secure_filename(f.filename)}"; f.save(os.path.join(app.config["UPLOAD_FOLDER"],name)); return name

@app.route("/tenants",methods=["GET","POST"])
@login_required
def tenants():
    if request.method=="POST":
        try:
            rid=int(request.form["room_id"]) if request.form.get("room_id") else None
            tenant = Tenant(full_name=request.form["full_name"],phone=request.form.get("phone"),cccd=request.form.get("cccd") or None,birth_date=datetime.strptime(request.form["birth_date"],"%Y-%m-%d").date() if request.form.get("birth_date") else None,gender=request.form.get("gender"),permanent_address=request.form.get("permanent_address"),move_in_date=datetime.strptime(request.form["move_in_date"],"%Y-%m-%d").date() if request.form.get("move_in_date") else None,room_id=rid,deposit=money("deposit"),notes=request.form.get("notes"),id_front=upload("id_front"),id_back=upload("id_back"),contract_file=upload("contract_file"))
            db.session.add(tenant); db.session.flush()
            if request.form.get("login_username") and request.form.get("login_password"):
                db.session.add(User(username=request.form["login_username"], full_name=tenant.full_name, password_hash=generate_password_hash(request.form["login_password"]), role="tenant", tenant_id=tenant.id))
            if rid: db.session.get(Room,rid).status="occupied"
            db.session.commit(); flash("Đã thêm người thuê.","success")
        except Exception: db.session.rollback(); flash("CCCD đã tồn tại hoặc dữ liệu không hợp lệ.","danger")
        return redirect(url_for("tenants"))
    return render_template("tenants.html",tenants=Tenant.query.order_by(Tenant.full_name).all(),rooms=Room.query.order_by(Room.code).all())

@app.route("/tenants/<int:id>/update", methods=["POST"])
@login_required
def update_tenant(id):
    tenant = db.get_or_404(Tenant, id)
    old_room_id = tenant.room_id
    try:
        tenant.full_name = request.form["full_name"]; tenant.phone = request.form.get("phone"); tenant.cccd = request.form.get("cccd") or None
        tenant.birth_date = datetime.strptime(request.form["birth_date"], "%Y-%m-%d").date() if request.form.get("birth_date") else None
        tenant.gender = request.form.get("gender"); tenant.permanent_address = request.form.get("permanent_address")
        tenant.move_in_date = datetime.strptime(request.form["move_in_date"], "%Y-%m-%d").date() if request.form.get("move_in_date") else None
        tenant.room_id = int(request.form["room_id"]) if request.form.get("room_id") else None; tenant.deposit = money("deposit"); tenant.notes = request.form.get("notes")
        tenant.id_front = upload("id_front") or tenant.id_front; tenant.id_back = upload("id_back") or tenant.id_back; tenant.contract_file = upload("contract_file") or tenant.contract_file
        if tenant.room_id: db.session.get(Room, tenant.room_id).status = "occupied"
        if old_room_id and old_room_id != tenant.room_id and not Tenant.query.filter(Tenant.room_id == old_room_id, Tenant.id != tenant.id).first(): db.session.get(Room, old_room_id).status = "vacant"
        db.session.commit(); flash("Đã cập nhật người thuê.", "success")
    except Exception:
        db.session.rollback(); flash("CCCD đã tồn tại hoặc dữ liệu không hợp lệ.", "danger")
    return redirect(url_for("tenants"))

@app.route("/tenants/<int:id>/delete", methods=["POST"])
@login_required
def delete_tenant(id):
    tenant = db.get_or_404(Tenant, id)
    room_id = tenant.room_id
    db.session.delete(tenant)
    db.session.flush()
    if room_id and not Tenant.query.filter_by(room_id=room_id).first(): db.session.get(Room, room_id).status = "vacant"
    db.session.commit(); flash("Đã xóa người thuê.", "success")
    return redirect(url_for("tenants"))

@app.route("/utilities",methods=["GET","POST"])
@login_required
def utilities():
    if request.method=="POST":
        oe,ne,ow,nw=money("old_electricity"),money("new_electricity"),money("old_water"),money("new_water")
        if ne<oe or nw<ow: flash("Chỉ số mới không được nhỏ hơn chỉ số cũ.","danger")
        else:
            try: db.session.add(UtilityReading(room_id=int(request.form["room_id"]),reading_month=month("reading_month"),old_electricity=oe,new_electricity=ne,electricity_rate=money("electricity_rate"),old_water=ow,new_water=nw,water_rate=money("water_rate"))); db.session.commit(); flash("Đã lưu chỉ số.","success")
            except Exception: db.session.rollback(); flash("Đã có chỉ số của phòng này trong tháng đã chọn.","danger")
        return redirect(url_for("utilities"))
    return render_template("utilities.html",readings=UtilityReading.query.order_by(UtilityReading.reading_month.desc()).all(),rooms=Room.query.order_by(Room.code).all())

@app.route("/utilities/previous")
@login_required
def previous_utility_reading():
    try:
        room_id = int(request.args["room_id"])
        selected_month = datetime.strptime(request.args["month"], "%Y-%m").date().replace(day=1)
    except (KeyError, ValueError):
        return jsonify({"error": "Dữ liệu phòng hoặc tháng không hợp lệ."}), 400
    previous = UtilityReading.query.filter(UtilityReading.room_id == room_id, UtilityReading.reading_month < selected_month).order_by(UtilityReading.reading_month.desc()).first()
    if not previous:
        return jsonify({"found": False})
    return jsonify({"found": True, "month": previous.reading_month.strftime("%m/%Y"), "old_electricity": str(previous.new_electricity), "old_water": str(previous.new_water)})

@app.route("/utilities/<int:id>/update", methods=["POST"])
@login_required
def update_utility(id):
    reading = db.get_or_404(UtilityReading, id)
    oe, ne, ow, nw = money("old_electricity"), money("new_electricity"), money("old_water"), money("new_water")
    if ne < oe or nw < ow:
        flash("Chỉ số mới không được nhỏ hơn chỉ số cũ.", "danger"); return redirect(url_for("utilities"))
    try:
        reading.room_id = int(request.form["room_id"]); reading.reading_month = month("reading_month")
        reading.old_electricity = oe; reading.new_electricity = ne; reading.electricity_rate = money("electricity_rate")
        reading.old_water = ow; reading.new_water = nw; reading.water_rate = money("water_rate")
        db.session.commit(); flash("Đã cập nhật chỉ số điện nước.", "success")
    except Exception:
        db.session.rollback(); flash("Phòng này đã có chỉ số trong tháng đã chọn.", "danger")
    return redirect(url_for("utilities"))

@app.route("/utilities/<int:id>/delete", methods=["POST"])
@login_required
def delete_utility(id):
    db.session.delete(db.get_or_404(UtilityReading, id)); db.session.commit()
    flash("Đã xóa chỉ số điện nước.", "success")
    return redirect(url_for("utilities"))

@app.route("/services",methods=["GET","POST"])
@login_required
def services():
    if request.method=="POST":
        try: db.session.add(Service(name=request.form["name"],unit_price=money("unit_price"),calculation=request.form["calculation"],is_active="is_active" in request.form)); db.session.commit(); flash("Đã thêm dịch vụ.","success")
        except Exception: db.session.rollback(); flash("Tên dịch vụ đã tồn tại.","danger")
        return redirect(url_for("services"))
    return render_template("services.html",services=Service.query.order_by(Service.name).all())

@app.route("/services/<int:id>/update", methods=["POST"])
@login_required
def update_service(id):
    service = db.get_or_404(Service, id)
    try:
        service.name = request.form["name"]; service.unit_price = money("unit_price")
        service.calculation = request.form["calculation"]; service.is_active = "is_active" in request.form
        db.session.commit(); flash("Đã cập nhật dịch vụ.", "success")
    except Exception:
        db.session.rollback(); flash("Tên dịch vụ đã tồn tại hoặc dữ liệu không hợp lệ.", "danger")
    return redirect(url_for("services"))

@app.route("/services/<int:id>/delete", methods=["POST"])
@login_required
def delete_service(id):
    db.session.delete(db.get_or_404(Service, id)); db.session.commit()
    flash("Đã xóa dịch vụ.", "success")
    return redirect(url_for("services"))

@app.route("/invoices",methods=["GET","POST"])
@login_required
def invoices():
    if current_user.role == "tenant" and request.method == "POST": abort(403)
    if request.method=="POST":
        room=db.session.get(Room,int(request.form["room_id"])); im=month("invoice_month"); reading=UtilityReading.query.filter_by(room_id=room.id,reading_month=im).first(); tenant=Tenant.query.filter_by(room_id=room.id).first()
        selected_services = selected_service_details(room); sf = sum((amount for _, amount in selected_services), Decimal("0")); ef=reading.electricity_fee if reading else Decimal("0"); wf=reading.water_fee if reading else Decimal("0"); extra=money("extra_fee"); discount=money("discount")
        try:
            invoice = Invoice(code=f"HD-{room.code}-{im:%Y%m}",room=room,tenant=tenant,invoice_month=im,room_fee=room.rent,electricity_fee=ef,water_fee=wf,service_fee=sf,extra_fee=extra,discount=discount,total=room.rent+ef+wf+sf+extra-discount,due_date=datetime.strptime(request.form["due_date"],"%Y-%m-%d").date() if request.form.get("due_date") else None,notes=request.form.get("notes"))
            invoice.details = [InvoiceDetail(description=f"{service.name} ({'theo người' if service.calculation == 'person' else 'theo phòng'})", amount=amount) for service, amount in selected_services]
            db.session.add(invoice); db.session.commit(); flash("Đã tạo hóa đơn.","success")
        except Exception: db.session.rollback(); flash("Phòng này đã có hóa đơn trong tháng đã chọn.","danger")
        return redirect(url_for("invoices"))
    invoice_query = Invoice.query
    if current_user.role == "tenant":
        if not current_user.tenant or not current_user.tenant.room_id: invoice_query = invoice_query.filter(False)
        else: invoice_query = invoice_query.filter_by(room_id=current_user.tenant.room_id)
        return render_template("tenant_invoices.html", invoices=invoice_query.order_by(Invoice.invoice_month.desc()).all())
    return render_template("invoices.html",invoices=invoice_query.order_by(Invoice.invoice_month.desc()).all(),rooms=Room.query.filter(Room.status!="maintenance").order_by(Room.code).all(),services=Service.query.filter_by(is_active=True).order_by(Service.name).all())

@app.route("/invoices/<int:id>/pay",methods=["POST"])
@login_required
def pay_invoice(id):
    if current_user.role != "admin": abort(403)
    inv=db.get_or_404(Invoice,id); amount=money("amount")
    if amount<=0 or amount>inv.balance: flash("Số tiền thanh toán không hợp lệ.","danger")
    else:
        db.session.add(Payment(invoice=inv,amount=amount,method=request.form.get("method","Tiền mặt"))); db.session.flush(); inv.status="paid" if inv.balance<=0 else "partial"; db.session.commit(); flash("Đã ghi nhận thanh toán.","success")
    return redirect(url_for("invoices"))

@app.route("/invoices/<int:id>/payment-request", methods=["POST"])
@login_required
def request_invoice_payment(id):
    if current_user.role != "tenant": abort(403)
    invoice = db.get_or_404(Invoice, id)
    if not current_user.tenant or invoice.room_id != current_user.tenant.room_id: abort(403)
    if invoice.status == "paid" or invoice.balance <= 0:
        flash("Hóa đơn này đã được thanh toán.", "info")
    elif invoice.pending_payment_request:
        flash("Yêu cầu thanh toán đang được xử lý.", "info")
    else:
        method = request.form.get("method", "")
        if method not in {"Tiền mặt", "Chuyển khoản"}:
            flash("Phương thức thanh toán không hợp lệ.", "danger")
        else:
            db.session.add(PaymentRequest(invoice=invoice, requester_id=current_user.id, amount=invoice.balance, method=method))
            db.session.commit()
            flash("Đã gửi yêu cầu thanh toán. Vui lòng chờ quản trị viên xác nhận.", "success")
    return redirect(url_for("invoices"))

@app.route("/payment-requests/<int:id>/approve", methods=["POST"])
@login_required
def approve_payment_request(id):
    if current_user.role != "admin": abort(403)
    payment_request = db.get_or_404(PaymentRequest, id)
    invoice = payment_request.invoice
    if payment_request.status != "pending":
        flash("Yêu cầu này đã được xử lý.", "info")
    elif invoice.balance <= 0:
        payment_request.status = "rejected"
        payment_request.processed_at = datetime.now()
        db.session.commit()
        flash("Hóa đơn đã được thanh toán trước đó nên yêu cầu đã đóng.", "info")
    else:
        amount = min(payment_request.amount, invoice.balance)
        db.session.add(Payment(invoice=invoice, amount=amount, method=payment_request.method, notes="Xác nhận từ yêu cầu của người thuê"))
        payment_request.status = "approved"
        payment_request.processed_at = datetime.now()
        db.session.flush()
        invoice.status = "paid" if invoice.balance <= 0 else "partial"
        db.session.commit()
        flash("Đã xác nhận thanh toán.", "success")
    return redirect(url_for("invoices"))

@app.route("/payment-requests/<int:id>/reject", methods=["POST"])
@login_required
def reject_payment_request(id):
    if current_user.role != "admin": abort(403)
    payment_request = db.get_or_404(PaymentRequest, id)
    if payment_request.status == "pending":
        payment_request.status = "rejected"
        payment_request.processed_at = datetime.now()
        db.session.commit()
        flash("Đã từ chối yêu cầu thanh toán.", "warning")
    else:
        flash("Yêu cầu này đã được xử lý.", "info")
    return redirect(url_for("invoices"))

@app.route("/invoices/<int:id>/update", methods=["POST"])
@login_required
def update_invoice(id):
    invoice = db.get_or_404(Invoice, id)
    try:
        room = db.session.get(Room, int(request.form["room_id"]))
        invoice_month = month("invoice_month")
        room_fee = money("room_fee"); electricity_fee = money("electricity_fee"); water_fee = money("water_fee")
        selected_services = selected_service_details(room); service_fee = sum((amount for _, amount in selected_services), Decimal("0")); extra_fee = money("extra_fee"); discount = money("discount")
        total = room_fee + electricity_fee + water_fee + service_fee + extra_fee - discount
        if total < 0: raise ValueError("Tổng tiền không thể âm")
        invoice.room = room; invoice.tenant = Tenant.query.filter_by(room_id=room.id).first(); invoice.invoice_month = invoice_month
        invoice.code = f"HD-{room.code}-{invoice_month:%Y%m}"; invoice.room_fee = room_fee; invoice.electricity_fee = electricity_fee
        invoice.water_fee = water_fee; invoice.service_fee = service_fee; invoice.extra_fee = extra_fee; invoice.discount = discount; invoice.total = total
        invoice.due_date = datetime.strptime(request.form["due_date"], "%Y-%m-%d").date() if request.form.get("due_date") else None; invoice.notes = request.form.get("notes")
        invoice.details = [InvoiceDetail(description=f"{service.name} ({'theo người' if service.calculation == 'person' else 'theo phòng'})", amount=amount) for service, amount in selected_services]
        invoice.status = "paid" if invoice.paid_amount >= total else ("partial" if invoice.paid_amount > 0 else "unpaid")
        db.session.commit(); flash("Đã cập nhật hóa đơn.", "success")
    except Exception:
        db.session.rollback(); flash("Không thể cập nhật. Kiểm tra trùng phòng/tháng hoặc các khoản tiền.", "danger")
    return redirect(url_for("invoices"))

@app.route("/invoices/<int:id>/delete", methods=["POST"])
@login_required
def delete_invoice(id):
    db.session.delete(db.get_or_404(Invoice, id)); db.session.commit()
    flash("Đã xóa hóa đơn và lịch sử thanh toán liên quan.", "success")
    return redirect(url_for("invoices"))

@app.route("/invoices/<int:id>/print")
@login_required
def print_invoice(id):
    invoice = db.get_or_404(Invoice, id)
    if current_user.role == "tenant" and (not current_user.tenant or invoice.room_id != current_user.tenant.room_id): abort(403)
    return render_template("print_invoice.html", invoice=invoice)

@app.route("/invoices/<int:id>/pdf")
@login_required
def pdf(id):
    inv = db.get_or_404(Invoice, id)
    if current_user.role == "tenant" and (not current_user.tenant or inv.room_id != current_user.tenant.room_id): abort(403)
    out = BytesIO(); regular, bold = "Helvetica", "Helvetica-Bold"
    font_dir = os.environ.get("WINDIR", "C:\\Windows") + "\\Fonts"
    if os.path.exists(os.path.join(font_dir, "arial.ttf")):
        try:
            pdfmetrics.registerFont(TTFont("InvoiceArial", os.path.join(font_dir, "arial.ttf")))
            pdfmetrics.registerFont(TTFont("InvoiceArialBold", os.path.join(font_dir, "arialbd.ttf")))
            regular, bold = "InvoiceArial", "InvoiceArialBold"
        except Exception: pass
    doc = SimpleDocTemplate(out, pagesize=A4, rightMargin=20*mm, leftMargin=20*mm, topMargin=18*mm, bottomMargin=18*mm)
    styles = getSampleStyleSheet(); title = ParagraphStyle("title", parent=styles["Normal"], fontName=bold, fontSize=18, leading=24, alignment=TA_CENTER, textColor=colors.HexColor("#102a43")); normal = ParagraphStyle("normal", parent=styles["Normal"], fontName=regular, fontSize=10, leading=15); strong = ParagraphStyle("strong", parent=normal, fontName=bold)
    story = [Paragraph("HÓA ĐƠN TIỀN PHÒNG", title), Spacer(1, 7*mm)]
    tenant = inv.tenant.full_name if inv.tenant else "-"
    info = [[Paragraph("<b>Mã hóa đơn:</b> " + inv.code, normal), Paragraph("<b>Tháng:</b> " + inv.invoice_month.strftime("%m/%Y"), normal)], [Paragraph("<b>Phòng:</b> " + inv.room.code + " - " + inv.room.name, normal), Paragraph("<b>Người thuê:</b> " + tenant, normal)]]
    info_table = Table(info, colWidths=[85*mm, 85*mm]); info_table.setStyle(TableStyle([("BOX", (0,0), (-1,-1), .5, colors.HexColor("#b8c5c2")), ("INNERGRID", (0,0), (-1,-1), .5, colors.HexColor("#d6dfdc")), ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#f4f8f7")), ("VALIGN", (0,0), (-1,-1), "MIDDLE"), ("LEFTPADDING", (0,0), (-1,-1), 8), ("TOPPADDING", (0,0), (-1,-1), 7), ("BOTTOMPADDING", (0,0), (-1,-1), 7)])); story += [info_table, Spacer(1, 7*mm)]
    rows = [[Paragraph("Khoản thu", strong), Paragraph("Số tiền", strong)], ["Tiền phòng", f"{inv.room_fee:,.0f} đ"], ["Tiền điện", f"{inv.electricity_fee:,.0f} đ"], ["Tiền nước", f"{inv.water_fee:,.0f} đ"]]
    for detail in inv.details: rows.append(["Dịch vụ: " + detail.description, f"{detail.amount:,.0f} đ"])
    if not inv.details: rows.append(["Dịch vụ", f"{inv.service_fee:,.0f} đ"])
    rows += [["Khoản phát sinh", f"{inv.extra_fee:,.0f} đ"], ["Giảm giá", f"-{inv.discount:,.0f} đ"], ["TỔNG CỘNG", f"{inv.total:,.0f} đ"], ["Đã thanh toán", f"{inv.paid_amount:,.0f} đ"], ["CÒN LẠI", f"{inv.balance:,.0f} đ"]]
    table = Table(rows, colWidths=[118*mm, 52*mm]); table.setStyle(TableStyle([("FONTNAME", (0,0), (-1,-1), regular), ("FONTNAME", (0,0), (-1,0), bold), ("FONTNAME", (0,-3), (-1,-1), bold), ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#dbece7")), ("BACKGROUND", (0,-3), (-1,-3), colors.HexColor("#e3f4ed")), ("BACKGROUND", (0,-1), (-1,-1), colors.HexColor("#fff4cf")), ("GRID", (0,0), (-1,-1), .5, colors.HexColor("#b8c5c2")), ("ALIGN", (1,0), (1,-1), "RIGHT"), ("VALIGN", (0,0), (-1,-1), "MIDDLE"), ("LEFTPADDING", (0,0), (-1,-1), 9), ("RIGHTPADDING", (0,0), (-1,-1), 9), ("TOPPADDING", (0,0), (-1,-1), 7), ("BOTTOMPADDING", (0,0), (-1,-1), 7)])); story.append(table)
    if inv.notes: story += [Spacer(1, 6*mm), Paragraph("<b>Ghi chú:</b> " + inv.notes, normal)]
    doc.build(story); out.seek(0)
    return send_file(out, as_attachment=True, download_name=f"{inv.code}.pdf", mimetype="application/pdf")

def seed():
    db.create_all()
    admin = User.query.filter_by(username="admin").first()
    if not admin: db.session.add(User(username="admin",full_name="Quản trị viên",password_hash=generate_password_hash("admin123"), role="admin"))
    elif not admin.role: admin.role = "admin"
    db.session.commit()
if __name__=="__main__":
    with app.app_context(): seed()
    app.run(debug=True)
