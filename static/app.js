document.addEventListener("submit", function (event) {
  var form = event.target;
  if (!form.classList || !form.classList.contains("js-confirm")) {
    return;
  }
  var message = form.getAttribute("data-confirm") || "Are you sure?";
  if (!window.confirm(message)) {
    event.preventDefault();
  }
});

document.addEventListener("click", function (event) {
  var printBtn = event.target.closest("[data-print]");
  if (printBtn) {
    event.preventDefault();
    window.print();
    return;
  }
  var themeBtn = event.target.closest("[data-theme-toggle]");
  if (themeBtn) {
    var current = document.documentElement.getAttribute("data-theme");
    var next = current === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try {
      localStorage.setItem("ost-theme", next);
    } catch (e) {
      /* ignore */
    }
  }
});

function visibleLabels(list) {
  return Array.prototype.filter.call(list.querySelectorAll("label[data-filter-text]"), function (label) {
    return label.style.display !== "none";
  });
}

function updateLabelCount() {
  var form = document.getElementById("label-form");
  if (!form) {
    return;
  }
  var count = form.querySelectorAll('input[type="checkbox"]:checked').length;
  var el = form.querySelector(".label-count");
  if (el) {
    el.textContent = count + " label" + (count === 1 ? "" : "s") + " selected";
  }
}

function bindLabelFilters() {
  var form = document.getElementById("label-form");
  if (!form) {
    return;
  }
  form.addEventListener("input", function (event) {
    var input = event.target.closest("[data-filter-input]");
    if (!input) {
      updateLabelCount();
      return;
    }
    var key = input.getAttribute("data-filter-input");
    var list = form.querySelector('[data-filter-list="' + key + '"]');
    if (!list) {
      return;
    }
    var q = (input.value || "").toLowerCase();
    list.querySelectorAll("label[data-filter-text]").forEach(function (label) {
      var text = (label.getAttribute("data-filter-text") || "").toLowerCase();
      label.style.display = !q || text.indexOf(q) !== -1 ? "" : "none";
    });
  });
  form.addEventListener("click", function (event) {
    var selectBtn = event.target.closest("[data-select-visible]");
    var clearBtn = event.target.closest("[data-clear-visible]");
    var key = selectBtn
      ? selectBtn.getAttribute("data-select-visible")
      : clearBtn
        ? clearBtn.getAttribute("data-clear-visible")
        : "";
    if (!key) {
      return;
    }
    event.preventDefault();
    var list = form.querySelector('[data-filter-list="' + key + '"]');
    if (!list) {
      return;
    }
    var checked = Boolean(selectBtn);
    visibleLabels(list).forEach(function (label) {
      var box = label.querySelector('input[type="checkbox"]');
      if (box) {
        box.checked = checked;
      }
    });
    updateLabelCount();
  });
  form.addEventListener("change", updateLabelCount);
  updateLabelCount();
}

function bindNavDrawer() {
  var drawer = document.querySelector(".nav-drawer");
  if (!drawer) {
    return;
  }
  var desktop = window.matchMedia("(min-width: 850px)");
  function syncDrawer(isDesktop) {
    if (isDesktop) {
      drawer.setAttribute("open", "");
    } else {
      drawer.removeAttribute("open");
    }
  }
  syncDrawer(desktop.matches);
  if (desktop.addEventListener) {
    desktop.addEventListener("change", function (event) {
      syncDrawer(event.matches);
    });
  } else if (desktop.addListener) {
    desktop.addListener(function (event) {
      syncDrawer(event.matches);
    });
  }
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && drawer.open && !desktop.matches) {
      drawer.removeAttribute("open");
    }
  });
}

function bindRoomPlaceSelects() {
  var room = document.getElementById("id_room");
  var place = document.getElementById("id_place");
  if (!room || !place) {
    return;
  }
  function syncPlaces() {
    var roomId = room.value;
    Array.prototype.forEach.call(place.options, function (opt) {
      if (!opt.value) {
        opt.hidden = false;
        return;
      }
      var match = !roomId || opt.getAttribute("data-room") === roomId;
      opt.hidden = !match;
      if (!match && opt.selected) {
        place.value = "";
      }
    });
  }
  room.addEventListener("change", syncPlaces);
  syncPlaces();
}

function dataUriToFile(uri, name) {
  var comma = uri.indexOf(",");
  if (comma < 0) {
    throw new Error("invalid data uri");
  }
  var binary = atob(uri.slice(comma + 1));
  var bytes = new Uint8Array(binary.length);
  var i;
  for (i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return new File([bytes], name, { type: "image/png" });
}

function bindSharePng() {
  document.querySelectorAll("[data-share-png]").forEach(function (btn) {
    btn.hidden = !navigator.share;
  });
  document.addEventListener("click", function (event) {
    var btn = event.target.closest("[data-share-png]");
    if (!btn) {
      return;
    }
    event.preventDefault();
    if (!navigator.share) {
      return;
    }
    var card = btn.closest(".label-preview-card");
    var img = card && card.querySelector("img.label-preview-img");
    var uri = btn.getAttribute("data-share-png") || (img && img.getAttribute("src")) || "";
    var name = btn.getAttribute("data-share-name") || "label.png";
    var file;
    var payload;
    try {
      file = dataUriToFile(uri, name);
      payload = { files: [file] };
    } catch (err) {
      return;
    }
    // Files only: iOS rejects title/text together with a PNG and then looks like a failed share.
    if (typeof navigator.canShare === "function" && !navigator.canShare(payload)) {
      return;
    }
    navigator.share(payload).catch(function (err) {
      if (err && (err.name === "AbortError" || err.name === "NotAllowedError")) {
        return;
      }
    });
  });
}

var SCAN_FORMATS = ["qr_code", "code_128"];

function scanLookupUrl() {
  return document.body.getAttribute("data-scan-lookup") || "";
}

function lookupScannedCode(raw, onHit, onMiss) {
  var url = scanLookupUrl();
  if (!url) {
    onMiss();
    return;
  }
  fetch(url + "?q=" + encodeURIComponent(raw), {
    headers: { Accept: "application/json" },
    credentials: "same-origin",
  })
    .then(function (res) {
      if (!res.ok) {
        onMiss();
        return null;
      }
      return res.json();
    })
    .then(function (data) {
      if (data && (data.url || data.short_url)) {
        onHit(data);
      } else if (data) {
        onMiss();
      }
    })
    .catch(function () {
      onMiss();
    });
}

function bindVideoScanner(opts) {
  var video = document.getElementById(opts.videoId);
  var startBtn = document.getElementById(opts.startId);
  var stopBtn = document.getElementById(opts.stopId);
  var statusEl = opts.statusId ? document.getElementById(opts.statusId) : null;
  if (!video || !startBtn) {
    return null;
  }
  var stage = video.closest(".stocktake-camera");
  if (!("BarcodeDetector" in window) || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    if (statusEl) {
      statusEl.textContent =
        "This browser cannot scan from the camera. Type the number below, or use Chrome or Safari.";
    }
    startBtn.hidden = true;
    if (stage) {
      stage.classList.add("no-detector");
    }
    return null;
  }
  var stream = null;
  var timer = null;
  var detector = null;
  var going = false;
  var lastTried = "";
  var inflight = false;

  function setLive(on) {
    if (stage) {
      stage.classList.toggle("is-live", on);
    }
  }

  function stop() {
    going = false;
    inflight = false;
    lastTried = "";
    if (timer) {
      window.clearTimeout(timer);
      timer = null;
    }
    if (stream) {
      stream.getTracks().forEach(function (track) {
        track.stop();
      });
      stream = null;
    }
    video.srcObject = null;
    setLive(false);
    if (stopBtn) {
      stopBtn.hidden = true;
    }
    startBtn.hidden = false;
  }

  function goTo(data) {
    var dest = opts.mode === "stocktake" ? data.short_url || data.url : data.url || data.short_url;
    if (!dest) {
      inflight = false;
      return;
    }
    stop();
    window.location.href = dest;
  }

  function handleValue(raw) {
    raw = (raw || "").trim();
    if (!raw || raw === lastTried || inflight) {
      return;
    }
    lastTried = raw;
    inflight = true;
    lookupScannedCode(
      raw,
      function (data) {
        goTo(data);
      },
      function () {
        inflight = false;
      }
    );
  }

  function tick() {
    if (!going || !detector || video.readyState < 2) {
      timer = window.setTimeout(tick, 250);
      return;
    }
    detector
      .detect(video)
      .then(function (codes) {
        var i;
        for (i = 0; i < codes.length; i += 1) {
          handleValue(codes[i].rawValue || "");
        }
        if (going) {
          timer = window.setTimeout(tick, 250);
        }
      })
      .catch(function () {
        if (going) {
          timer = window.setTimeout(tick, 400);
        }
      });
  }

  function withDetector(done) {
    if (detector) {
      done(detector);
      return;
    }
    function make(formats) {
      detector = new BarcodeDetector({ formats: formats });
      done(detector);
    }
    if (!BarcodeDetector.getSupportedFormats) {
      make(SCAN_FORMATS);
      return;
    }
    BarcodeDetector.getSupportedFormats()
      .then(function (supported) {
        var formats = SCAN_FORMATS.filter(function (f) {
          return supported.indexOf(f) !== -1;
        });
        make(formats.length ? formats : ["qr_code"]);
      })
      .catch(function () {
        make(SCAN_FORMATS);
      });
  }

  function start() {
    if (going || stream) {
      return;
    }
    withDetector(function () {});
    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: "environment" }, audio: false })
      .then(function (media) {
        stream = media;
        video.srcObject = media;
        setLive(true);
        startBtn.hidden = true;
        if (stopBtn) {
          stopBtn.hidden = false;
        }
        going = true;
        tick();
      })
      .catch(function () {
        startBtn.hidden = false;
        startBtn.textContent = "Camera unavailable";
        if (statusEl) {
          statusEl.textContent = "Allow the camera, or type the number below.";
        }
      });
  }

  startBtn.addEventListener("click", start);
  if (stopBtn) {
    stopBtn.addEventListener("click", stop);
  }
  if (opts.dialog) {
    opts.dialog.addEventListener("close", stop);
    opts.dialog._scanStart = start;
  }
  return stop;
}

function bindLabelScanners() {
  bindVideoScanner({
    videoId: "stocktake-video",
    startId: "stocktake-camera-start",
    stopId: "stocktake-camera-stop",
    statusId: "stocktake-camera-fallback",
    mode: "stocktake",
  });
  var dialog = document.getElementById("scan-lookup-dialog");
  bindVideoScanner({
    videoId: "scan-lookup-video",
    startId: "scan-lookup-start",
    stopId: "scan-lookup-stop",
    statusId: "scan-lookup-status",
    mode: "lookup",
    dialog: dialog,
  });
}

function bindManualScan() {
  document.addEventListener("submit", function (event) {
    var form = event.target.closest("[data-scan-manual]");
    if (!form) {
      return;
    }
    event.preventDefault();
    var input = form.querySelector("input[name='q']");
    var miss = document.getElementById(form.getAttribute("data-scan-miss") || "");
    var raw = input ? input.value.trim() : "";
    if (miss) {
      miss.hidden = true;
    }
    if (!raw) {
      return;
    }
    lookupScannedCode(
      raw,
      function (data) {
        var dest =
          form.getAttribute("data-scan-mode") === "stocktake"
            ? data.short_url || data.url
            : data.url || data.short_url;
        if (dest) {
          window.location.href = dest;
        }
      },
      function () {
        if (miss) {
          miss.hidden = false;
        }
      }
    );
  });
}

function bindDialogs() {
  document.addEventListener("click", function (event) {
    var openBtn = event.target.closest("[data-dialog-open]");
    if (openBtn) {
      var dialog = document.getElementById(openBtn.getAttribute("data-dialog-open"));
      if (dialog && dialog.showModal) {
        dialog.showModal();
        if (typeof dialog._scanStart === "function") {
          dialog._scanStart();
        }
      }
      return;
    }
    var closeBtn = event.target.closest("[data-dialog-close]");
    if (closeBtn) {
      var dialog = closeBtn.closest("dialog");
      if (dialog) {
        dialog.close();
      }
    }
  });
  document.querySelectorAll("dialog.ost-dialog").forEach(function (dialog) {
    dialog.addEventListener("click", function (event) {
      if (event.target === dialog) {
        dialog.close();
      }
    });
  });
}

function bindPhotoCapture() {
  document.addEventListener("change", function (event) {
    var input = event.target.closest(".js-photo-capture input[type='file']");
    if (!input || !input.files || !input.files.length) {
      return;
    }
    var form = input.form;
    if (!form) {
      return;
    }
    var message = form.getAttribute("data-confirm");
    if (message && !window.confirm(message)) {
      input.value = "";
      return;
    }
    if (form.requestSubmit) {
      form.requestSubmit();
    } else {
      form.submit();
    }
  });
}

function bindItemHostPickers() {
  document.querySelectorAll(".item-host-picker").forEach(function (picker) {
    var search = picker.querySelector("[data-host-search]");
    var results = picker.querySelector(".item-host-results");
    var select = picker.querySelector("select");
    var lookupUrl = picker.getAttribute("data-lookup-url");
    if (!search || !results || !select || !lookupUrl) {
      return;
    }
    var timer = null;
    var exclude = picker.getAttribute("data-exclude") || "";

    function setHost(id, label) {
      var value = id ? String(id) : "";
      if (value) {
        var found = false;
        Array.prototype.forEach.call(select.options, function (opt) {
          if (opt.value === value) {
            found = true;
          }
        });
        if (!found) {
          select.appendChild(new Option(label, value));
        }
      }
      select.value = value;
      results.hidden = true;
      results.replaceChildren();
      search.value = "";
    }

    function renderRows(rows) {
      results.replaceChildren();
      if (!rows.length) {
        var empty = document.createElement("p");
        empty.className = "muted";
        empty.textContent = "No matching items.";
        results.appendChild(empty);
        results.hidden = false;
        return;
      }
      rows.forEach(function (row) {
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "outline secondary";
        btn.textContent = row.label;
        if (row.location) {
          var loc = document.createElement("span");
          loc.className = "muted";
          loc.textContent = " · " + row.location;
          btn.appendChild(loc);
        }
        btn.addEventListener("click", function () {
          setHost(row.id, row.label);
        });
        results.appendChild(btn);
      });
      results.hidden = false;
    }

    search.addEventListener("input", function () {
      var q = (search.value || "").trim();
      window.clearTimeout(timer);
      if (!q) {
        results.hidden = true;
        results.replaceChildren();
        return;
      }
      timer = window.setTimeout(function () {
        var url = lookupUrl + "?q=" + encodeURIComponent(q);
        if (exclude) {
          url += "&exclude=" + encodeURIComponent(exclude);
        }
        fetch(url, { headers: { Accept: "application/json" }, credentials: "same-origin" })
          .then(function (res) {
            if (!res.ok) {
              return { results: [] };
            }
            return res.json();
          })
          .then(function (data) {
            renderRows((data && data.results) || []);
          })
          .catch(function () {
            renderRows([]);
          });
      }, 200);
    });
  });
}

function bindUi() {
  bindLabelFilters();
  bindNavDrawer();
  bindRoomPlaceSelects();
  bindItemHostPickers();
  bindSharePng();
  bindLabelScanners();
  bindManualScan();
  bindDialogs();
  bindPhotoCapture();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", bindUi);
} else {
  bindUi();
}
