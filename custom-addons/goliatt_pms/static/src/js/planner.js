/** @odoo-module **/
import { Component, useState, useRef, onMounted, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

const CELL_WIDTH = 44;
const ROW_HEIGHT = 32;
const HEADER_HEIGHT = 52 + 42; // toolbar + header row
const LABEL_WIDTH = 140;
const DAYS_TO_SHOW = 28;

class PmsPlanner extends Component {
    static template = "goliatt_pms.PlannerView";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.barsRef = useRef("barsContainer");

        this.state = useState({
            dates: [],
            rooms: [],
            reservations: [],
            bars: [],
            periodLabel: "",
            startDate: null,
        });

        this._dragging = null;
        this._resizing = null;

        onMounted(() => {
            this._setStartDate(this._today());
            this._loadData();
        });
    }

    // ── Date helpers ──────────────────────────────────────

    _today() {
        const d = new Date();
        return new Date(d.getFullYear(), d.getMonth(), d.getDate());
    }

    _toISO(d) {
        return d.toISOString().slice(0, 10);
    }

    _addDays(d, n) {
        const r = new Date(d);
        r.setDate(r.getDate() + n);
        return r;
    }

    _diffDays(a, b) {
        return Math.round((b - a) / 86400000);
    }

    _dayNames() {
        return ["Dom", "Lun", "Mar", "Mié", "Jue", "Vie", "Sáb"];
    }

    _monthNames() {
        return ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];
    }

    _setStartDate(d) {
        this.state.startDate = d;
        const dates = [];
        const today = this._toISO(this._today());
        for (let i = 0; i < DAYS_TO_SHOW; i++) {
            const dt = this._addDays(d, i);
            const dow = dt.getDay();
            dates.push({
                date: dt,
                iso: this._toISO(dt),
                dayNum: dt.getDate(),
                dayName: this._dayNames()[dow],
                isWeekend: dow === 0 || dow === 6,
                isToday: this._toISO(dt) === today,
            });
        }
        this.state.dates = dates;
        const endDate = this._addDays(d, DAYS_TO_SHOW - 1);
        this.state.periodLabel = `${this._monthNames()[d.getMonth()]} ${d.getDate()} — ${this._monthNames()[endDate.getMonth()]} ${endDate.getDate()}, ${endDate.getFullYear()}`;
    }

    // ── Data loading ──────────────────────────────────────

    async _loadData() {
        const startISO = this._toISO(this.state.startDate);
        const endISO = this._toISO(this._addDays(this.state.startDate, DAYS_TO_SHOW));

        // Load rooms
        const rooms = await this.orm.searchRead("pms.room", [["active", "=", true]], ["name", "room_type_id", "floor", "status", "housekeeping_status"], { order: "name", limit: 200 });
        this.state.rooms = rooms.map((r) => ({
            id: r.id,
            name: r.name,
            room_type: r.room_type_id ? r.room_type_id[1] : "",
            floor: r.floor,
            status: r.status,
        }));

        // Load reservations overlapping this period
        const reservations = await this.orm.searchRead(
            "pms.reservation",
            [
                ["checkin_date", "<", endISO],
                ["checkout_date", ">", startISO],
                ["state", "not in", ["cancelled"]],
            ],
            ["name", "guest_id", "checkin_date", "checkout_date", "room_id", "room_type_id", "state", "adults", "nights", "daily_rate"],
            { order: "checkin_date", limit: 500 }
        );
        this.state.reservations = reservations;

        this._computeBars();
    }

    _computeBars() {
        const bars = [];
        const startDate = this.state.startDate;
        const roomIndexMap = {};
        this.state.rooms.forEach((r, idx) => {
            roomIndexMap[r.id] = idx;
        });

        for (const res of this.state.reservations) {
            if (!res.room_id) continue;
            const roomId = res.room_id[0];
            const roomIdx = roomIndexMap[roomId];
            if (roomIdx === undefined) continue;

            const checkin = new Date(res.checkin_date + "T00:00:00");
            const checkout = new Date(res.checkout_date + "T00:00:00");

            const startOffset = Math.max(0, this._diffDays(startDate, checkin));
            const endOffset = Math.min(DAYS_TO_SHOW, this._diffDays(startDate, checkout));

            if (endOffset <= 0 || startOffset >= DAYS_TO_SHOW) continue;

            const left = LABEL_WIDTH + startOffset * CELL_WIDTH;
            const width = (endOffset - startOffset) * CELL_WIDTH - 2;
            const top = HEADER_HEIGHT + roomIdx * ROW_HEIGHT;

            bars.push({
                id: res.id,
                left,
                top,
                width: Math.max(width, 20),
                guestName: res.guest_id ? res.guest_id[1] : res.name,
                state: res.state,
                nights: res.nights,
                checkinDate: res.checkin_date,
                checkoutDate: res.checkout_date,
                roomId,
            });
        }
        this.state.bars = bars;
    }

    // ── Navigation ────────────────────────────────────────

    onPrevPeriod() {
        this._setStartDate(this._addDays(this.state.startDate, -14));
        this._loadData();
    }

    onNextPeriod() {
        this._setStartDate(this._addDays(this.state.startDate, 14));
        this._loadData();
    }

    onToday() {
        this._setStartDate(this._addDays(this._today(), -3));
        this._loadData();
    }

    onRefresh() {
        this._loadData();
    }

    // ── Cell click → create reservation ───────────────────

    async onCellClick(ev) {
        if (this._dragging || this._resizing) return;
        const roomId = parseInt(ev.currentTarget.dataset.roomId);
        const dateStr = ev.currentTarget.dataset.date;
        if (!roomId || !dateStr) return;

        // Open reservation form with prefilled data
        const room = await this.orm.read("pms.room", [roomId], ["room_type_id", "property_id"]);
        if (!room.length) return;

        const checkout = this._toISO(this._addDays(new Date(dateStr + "T00:00:00"), 1));

        this.action.doAction({
            type: "ir.actions.act_window",
            name: _t("New Reservation"),
            res_model: "pms.reservation",
            view_mode: "form",
            views: [[false, "form"]],
            target: "new",
            context: {
                default_property_id: room[0].property_id[0],
                default_room_type_id: room[0].room_type_id[0],
                default_room_id: roomId,
                default_checkin_date: dateStr,
                default_checkout_date: checkout,
            },
        });
    }

    // ── Bar click → open reservation ──────────────────────

    async onBarClick(ev) {
        ev.stopPropagation();
        if (this._dragging || this._resizing) return;
        const resId = parseInt(ev.currentTarget.dataset.resId);
        if (!resId) return;

        this.action.doAction({
            type: "ir.actions.act_window",
            name: _t("Reservation"),
            res_model: "pms.reservation",
            res_id: resId,
            view_mode: "form",
            views: [[false, "form"]],
            target: "new",
        });
    }

    // ── Drag to move reservation ──────────────────────────

    onBarMouseDown(ev) {
        if (ev.target.classList.contains("resize-handle")) return;
        ev.preventDefault();
        ev.stopPropagation();

        const resId = parseInt(ev.currentTarget.dataset.resId);
        const bar = this.state.bars.find((b) => b.id === resId);
        if (!bar || bar.state === "checked_out") return;

        this._dragging = {
            resId,
            startX: ev.clientX,
            startY: ev.clientY,
            origLeft: bar.left,
            origTop: bar.top,
            bar,
        };
        ev.currentTarget.classList.add("dragging");
    }

    onGridMouseMove(ev) {
        if (this._dragging) {
            const dx = ev.clientX - this._dragging.startX;
            const dy = ev.clientY - this._dragging.startY;
            const bar = this.state.bars.find((b) => b.id === this._dragging.resId);
            if (bar) {
                bar.left = this._dragging.origLeft + dx;
                bar.top = this._dragging.origTop + dy;
            }
        }
        if (this._resizing) {
            const dx = ev.clientX - this._resizing.startX;
            const bar = this.state.bars.find((b) => b.id === this._resizing.resId);
            if (bar) {
                bar.width = Math.max(CELL_WIDTH, this._resizing.origWidth + dx);
            }
        }
    }

    async onGridMouseUp(ev) {
        if (this._dragging) {
            const { resId, origLeft, origTop } = this._dragging;
            const bar = this.state.bars.find((b) => b.id === resId);
            if (bar) {
                // Calculate new room and date from position
                const newDateIdx = Math.round((bar.left - LABEL_WIDTH) / CELL_WIDTH);
                const newRoomIdx = Math.round((bar.top - HEADER_HEIGHT) / ROW_HEIGHT);

                const clampedDateIdx = Math.max(0, Math.min(DAYS_TO_SHOW - 1, newDateIdx));
                const clampedRoomIdx = Math.max(0, Math.min(this.state.rooms.length - 1, newRoomIdx));

                const newCheckin = this.state.dates[clampedDateIdx]?.iso;
                const newRoom = this.state.rooms[clampedRoomIdx];

                if (newCheckin && newRoom) {
                    const res = this.state.reservations.find((r) => r.id === resId);
                    if (res) {
                        const nights = res.nights || 1;
                        const newCheckout = this._toISO(this._addDays(new Date(newCheckin + "T00:00:00"), nights));

                        try {
                            await this.orm.write("pms.reservation", [resId], {
                                checkin_date: newCheckin,
                                checkout_date: newCheckout,
                                room_id: newRoom.id,
                            });
                            this.notification.add(_t("Reservation moved"), { type: "success" });
                        } catch (e) {
                            this.notification.add(_t("Could not move reservation"), { type: "danger" });
                        }
                    }
                }
            }
            document.querySelectorAll(".dragging").forEach((el) => el.classList.remove("dragging"));
            this._dragging = null;
            await this._loadData();
        }

        if (this._resizing) {
            const { resId, origWidth } = this._resizing;
            const bar = this.state.bars.find((b) => b.id === resId);
            if (bar) {
                const newNights = Math.max(1, Math.round(bar.width / CELL_WIDTH));
                const res = this.state.reservations.find((r) => r.id === resId);
                if (res) {
                    const newCheckout = this._toISO(this._addDays(new Date(res.checkin_date + "T00:00:00"), newNights));
                    try {
                        await this.orm.write("pms.reservation", [resId], {
                            checkout_date: newCheckout,
                        });
                        this.notification.add(_t("Stay length adjusted to " + newNights + " nights"), { type: "success" });
                    } catch (e) {
                        this.notification.add(_t("Could not adjust stay length"), { type: "danger" });
                    }
                }
            }
            this._resizing = null;
            await this._loadData();
        }
    }

    // ── Resize to adjust stay length ──────────────────────

    onResizeMouseDown(ev) {
        ev.preventDefault();
        ev.stopPropagation();

        const resId = parseInt(ev.currentTarget.dataset.resId);
        const bar = this.state.bars.find((b) => b.id === resId);
        if (!bar || bar.state === "checked_out") return;

        this._resizing = {
            resId,
            startX: ev.clientX,
            origWidth: bar.width,
        };
    }

    // ── Unused stubs ──────────────────────────────────────
    onCellMouseDown() {}
}

// Register as a client action
registry.category("actions").add("pms_planner", PmsPlanner);
