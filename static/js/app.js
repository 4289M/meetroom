/* MeetRoom – JavaScript (vanilla) */
(function () {
  "use strict";

  function pad(n) { return String(n).padStart(2, "0"); }
  function toHM(min) { return pad(Math.floor(min / 60)) + ":" + pad(min % 60); }
  function toMin(hm) { var p = hm.split(":"); return (+p[0]) * 60 + (+p[1]); }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  // ปิด flash message
  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-dismiss]");
    if (btn) btn.parentElement.remove();
  });

  // ยืนยันก่อนส่งฟอร์มอันตราย (ยกเลิก/ลบ/ไม่อนุมัติ)
  document.addEventListener("submit", function (e) {
    var submitter = e.submitter;
    var msg = (submitter && submitter.dataset.confirm) || e.target.dataset.confirm;
    if (msg && !window.confirm(msg)) e.preventDefault();
  });

  // เลือกวันที่แล้วไปทันที
  document.querySelectorAll("form[data-autosubmit] input[type=date]").forEach(function (input) {
    input.addEventListener("change", function () { if (input.value) input.form.submit(); });
  });

  // ---------------- Timeline ----------------
  var timeline = document.querySelector(".timeline");
  if (timeline) {
    var dayStart = +timeline.dataset.dayStart;
    var dayEnd = +timeline.dataset.dayEnd;
    var span = dayEnd - dayStart;

    function slotAt(track, clientX) {
      var rect = track.getBoundingClientRect();
      var ratio = Math.min(Math.max((clientX - rect.left) / rect.width, 0), 0.9999);
      return dayStart + Math.floor((ratio * span) / 30) * 30;
    }

    timeline.querySelectorAll(".tl-track").forEach(function (track) {
      var ghost = track.querySelector(".tl-ghost");
      track.addEventListener("mousemove", function (e) {
        if (e.target.closest(".tl-block")) { ghost.classList.remove("show"); return; }
        var start = slotAt(track, e.clientX);
        ghost.style.left = ((start - dayStart) / span * 100) + "%";
        ghost.textContent = toHM(start);
        ghost.classList.add("show");
      });
      track.addEventListener("mouseleave", function () { ghost.classList.remove("show"); });
      track.addEventListener("click", function (e) {
        if (e.target.closest(".tl-block")) return;
        var start = slotAt(track, e.clientX);
        var end = Math.min(start + 60, dayEnd);
        var params = new URLSearchParams({
          room_id: track.dataset.roomId,
          date: timeline.dataset.date,
          start: toHM(start),
          end: toHM(end)
        });
        window.location.href = timeline.dataset.newUrl + "?" + params.toString();
      });
    });

    // เลื่อนเส้นเวลาปัจจุบันทุกนาที
    var nowLine = document.getElementById("tl-now");
    if (nowLine) {
      setInterval(function () {
        var d = new Date();
        var m = d.getHours() * 60 + d.getMinutes();
        if (m < dayStart || m > dayEnd) { nowLine.style.display = "none"; return; }
        nowLine.style.left = ((m - dayStart) / span * 100) + "%";
      }, 60000);
    }
  }

  // ---------------- Booking form ----------------
  var form = document.getElementById("booking-form");
  if (form) {
    var el = function (name) { return form.elements[name]; };
    var availBox = document.getElementById("avail-box");
    var schedList = document.getElementById("schedule-list");
    var roomInfo = document.getElementById("room-info");
    var schedDate = document.getElementById("schedule-date");
    var excludeId = form.dataset.excludeId || "";
    var apiAvail = form.dataset.apiAvailability;
    var apiSched = form.dataset.apiSchedule;

    // เวลาสิ้นสุดต้องหลังเวลาเริ่ม: ถ้าผู้ใช้เลื่อนเวลาเริ่มเลยเวลาสิ้นสุด ให้ขยับให้อัตโนมัติ
    el("start_time").addEventListener("change", function () {
      var s = el("start_time").value, e = el("end_time").value;
      if (s && (!e || toMin(e) <= toMin(s))) el("end_time").value = toHM(Math.min(toMin(s) + 60, 18 * 60));
      hideAvail();
    });

    // การจองซ้ำ: เปิด/ปิดช่องจำนวนครั้ง
    var repeat = el("repeat");
    var repeatCount = el("repeat_count");
    function syncRepeat() {
      if (!repeat || !repeatCount) return;
      repeatCount.disabled = repeat.value === "none";
    }
    if (repeat) { repeat.addEventListener("change", syncRepeat); syncRepeat(); }

    function hideAvail() { if (availBox) availBox.hidden = true; }
    ["end_time", "attendees"].forEach(function (n) {
      if (el(n)) el(n).addEventListener("change", hideAvail);
    });

    function loadSchedule() {
      var roomId = el("room_id").value, date = el("booking_date").value;
      hideAvail();
      if (!roomId || !date) return;
      var url = apiSched + "?" + new URLSearchParams({ room_id: roomId, date: date, exclude_id: excludeId });
      fetch(url, { headers: { Accept: "application/json" } })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.error) return;
          renderSchedule(data);
          renderRoom(data.room);
          if (schedDate) schedDate.textContent = thaiDate(date);
        })
        .catch(function () { /* เงียบไว้ ฝั่ง server ตรวจซ้ำอยู่แล้ว */ });
    }

    var DAYS = ["อาทิตย์", "จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์"];
    var MONTHS = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน", "กรกฎาคม",
      "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"];
    function thaiDate(iso) {
      var p = iso.split("-"), d = new Date(+p[0], +p[1] - 1, +p[2]);
      return DAYS[d.getDay()] + " " + d.getDate() + " " + MONTHS[d.getMonth()] + " " + (d.getFullYear() + 543);
    }

    function renderSchedule(data) {
      if (!schedList) return;
      var items = [];
      data.busy.forEach(function (b) {
        items.push({ start: b.start_time, html:
          '<li class="slot slot-busy' + (b.mine ? " mine" : "") + (b.status === "pending" ? " pending" : "") + '">' +
          "<time>" + esc(b.start_time) + "–" + esc(b.end_time) + "</time>" +
          '<span class="slot-title" title="' + esc(b.title) + '">' + esc(b.title) +
          (b.status === "pending" ? " (รออนุมัติ)" : "") + "</span></li>" });
      });
      data.free.forEach(function (f) {
        items.push({ start: f.start, html:
          '<li class="slot slot-free"><time>' + esc(f.start) + "–" + esc(f.end) + "</time><span>ว่าง</span></li>" });
      });
      items.sort(function (a, b) { return a.start < b.start ? -1 : 1; });
      schedList.innerHTML = items.length ? items.map(function (i) { return i.html; }).join("")
        : '<li class="muted">ไม่มีข้อมูล</li>';
    }

    function renderRoom(room) {
      if (!roomInfo) return;
      roomInfo.innerHTML =
        "<dt>ห้อง</dt><dd>" + esc(room.name) + "</dd>" +
        "<dt>ที่ตั้ง</dt><dd>" + esc(room.location || "-") + "</dd>" +
        "<dt>ความจุ</dt><dd>" + esc(room.capacity) + " คน</dd>" +
        "<dt>อุปกรณ์</dt><dd>" + esc(room.equipment || "-") + "</dd>" +
        "<dt>การอนุมัติ</dt><dd>" + (room.require_approval
          ? '<span class="badge badge-pending">ต้องรอผู้ดูแลอนุมัติ</span>'
          : '<span class="badge badge-confirmed">ยืนยันทันที</span>') + "</dd>";
      var att = el("attendees");
      if (att) att.max = room.capacity;
      var capHint = document.getElementById("capacity-hint");
      if (capHint) capHint.textContent = "ห้องนี้จุได้สูงสุด " + room.capacity + " คน";
    }

    el("room_id").addEventListener("change", loadSchedule);
    el("booking_date").addEventListener("change", loadSchedule);

    // ปุ่มตรวจสอบห้องว่าง
    var checkBtn = document.getElementById("check-availability");
    if (checkBtn) {
      checkBtn.addEventListener("click", function () {
        var params = {
          room_id: el("room_id").value,
          date: el("booking_date").value,
          start: el("start_time").value,
          end: el("end_time").value,
          attendees: el("attendees").value || 1,
          exclude_id: excludeId
        };
        if (!params.room_id || !params.date || !params.start || !params.end) {
          showAvail(false, "<h3>ข้อมูลไม่ครบ</h3><p>กรุณาเลือกห้อง วันที่ และเวลาให้ครบ</p>");
          return;
        }
        checkBtn.disabled = true;
        fetch(apiAvail + "?" + new URLSearchParams(params), { headers: { Accept: "application/json" } })
          .then(function (r) { return r.json(); })
          .then(function (data) {
            if (data.error) { showAvail(false, "<h3>ตรวจสอบไม่ได้</h3><p>" + esc(data.error) + "</p>"); return; }
            if (data.available) {
              showAvail(true, "<h3>✓ ห้องว่าง</h3><p>" + esc(data.room.name) + " ว่างช่วง " +
                esc(params.start) + "–" + esc(params.end) + " น. สามารถจองได้</p>");
              return;
            }
            var html = "<h3>✕ ห้องไม่ว่าง</h3>";
            if (!data.room.is_active) html += "<p>ห้องนี้ปิดให้จองชั่วคราว</p>";
            if (data.conflicts.length) {
              html += "<p>ชนกับการจองต่อไปนี้:</p><ul>" + data.conflicts.map(function (c) {
                return "<li>" + esc(c.start) + "–" + esc(c.end) + " " + esc(c.title) +
                  (c.status === "pending" ? " (รออนุมัติ)" : "") + "</li>";
              }).join("") + "</ul>";
            }
            if (data.suggestions.length) {
              html += '<p style="margin-top:8px">ห้องอื่นที่ว่างช่วงเดียวกันและจุคนได้พอ:</p><div class="suggest-list">' +
                data.suggestions.map(function (s) {
                  return '<button type="button" class="btn btn-sm" data-pick-room="' + s.id + '">' +
                    esc(s.name) + " · " + esc(s.location) + " · " + s.capacity + " ที่</button>";
                }).join("") + "</div>";
            } else {
              html += '<p style="margin-top:8px">ไม่มีห้องอื่นที่ว่างและจุคนได้พอในช่วงนี้</p>';
            }
            showAvail(false, html);
          })
          .catch(function () { showAvail(false, "<h3>เชื่อมต่อไม่ได้</h3><p>กรุณาลองใหม่อีกครั้ง</p>"); })
          .finally(function () { checkBtn.disabled = false; });
      });
    }

    function showAvail(ok, html) {
      availBox.className = "avail-box " + (ok ? "ok" : "bad");
      availBox.innerHTML = html;
      availBox.hidden = false;
    }

    // เลือกห้องที่แนะนำ
    document.addEventListener("click", function (e) {
      var b = e.target.closest("[data-pick-room]");
      if (!b) return;
      el("room_id").value = b.dataset.pickRoom;
      loadSchedule();
      if (checkBtn) setTimeout(function () { checkBtn.click(); }, 50);
    });
  }
})();
