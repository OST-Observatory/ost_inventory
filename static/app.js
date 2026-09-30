// CSRF and fetch(): CSRF_COOKIE_HTTPONLY is True, so document.cookie does NOT
// contain "ost_inventory_csrftoken" and never will. The fetch() calls below are
// GETs, which need no token. If you add a POST/PUT/DELETE here and it comes back
// 403 ("CSRF cookie not set" / "CSRF token missing"), that is the reason: read
// the token from a {% csrf_token %} hidden input in the DOM, e.g.
//   document.querySelector("input[name=csrfmiddlewaretoken]").value
// and send it as the X-CSRFToken header. Do not turn the setting off.
// See config/settings.py (CSRF_COOKIE_HTTPONLY) and README "Security".

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
  document.querySelectorAll("select[data-room-select]").forEach(bindRoomPlaceSelect);
}

function bindRoomPlaceSelect(place) {
  var room = document.getElementById(place.getAttribute("data-room-select"));
  if (!room) {
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

function canShareData(data) {
  if (typeof navigator.share !== "function") {
    return false;
  }
  if (typeof navigator.canShare !== "function") {
    return true;
  }
  try {
    return navigator.canShare(data);
  } catch (err) {
    return false;
  }
}

function shareData(payload) {
  return navigator.share(payload).catch(function (err) {
    if (err && (err.name === "AbortError" || err.name === "NotAllowedError")) {
      return;
    }
    throw err;
  });
}

function labelPngUrl(btn) {
  var href = btn.getAttribute("data-share-href") || "";
  var card;
  var link;
  if (!href) {
    card = btn.closest(".label-preview-card");
    link = card && card.querySelector("a[download]");
    href = (link && (link.getAttribute("href") || link.href)) || "";
  }
  if (!href) {
    return "";
  }
  try {
    return new URL(href, window.location.href).href;
  } catch (err) {
    return href;
  }
}

function bindSharePng() {
  document.querySelectorAll("[data-share-png]").forEach(function (btn) {
    btn.hidden = typeof navigator.share !== "function";
  });
  document.addEventListener("click", function (event) {
    var btn = event.target.closest("[data-share-png]");
    if (!btn) {
      return;
    }
    event.preventDefault();
    if (typeof navigator.share !== "function") {
      return;
    }
    var card = btn.closest(".label-preview-card");
    var img = card && card.querySelector("img.label-preview-img");
    var uri = btn.getAttribute("data-share-png") || (img && img.getAttribute("src")) || "";
    var name = btn.getAttribute("data-share-name") || "label.png";
    var pngUrl = labelPngUrl(btn);
    var file;
    var filesPayload;
    try {
      file = dataUriToFile(uri, name);
      filesPayload = { files: [file] };
    } catch (err) {
      filesPayload = null;
    }
    // Files only: iOS rejects title/text together with a PNG.
    // Firefox/Fennec implement share() but not file attachments.
    if (filesPayload && canShareData(filesPayload)) {
      shareData(filesPayload).catch(function () {
        if (pngUrl && canShareData({ url: pngUrl })) {
          return shareData({ url: pngUrl });
        }
      });
      return;
    }
    if (pngUrl && canShareData({ url: pngUrl })) {
      shareData({ url: pngUrl });
    }
  });
}

var SCAN_FORMATS = ["qr_code", "code_128"];

function cameraScanSupported() {
  return (
    "BarcodeDetector" in window &&
    Boolean(navigator.mediaDevices && navigator.mediaDevices.getUserMedia)
  );
}

function cameraScanUnsupportedText() {
  if (window.isSecureContext === false) {
    return "The camera needs an HTTPS connection. Type the number instead, e.g. #0012.";
  }
  return (
    "This browser cannot read labels with the camera (iPhone, iPad and Firefox cannot). " +
    "Use Chrome on Android, or type the number, e.g. #0012."
  );
}

var SCAN_CAMERA_KEY = "ost-scan-camera";
var SCAN_ZOOM_KEY = "ost-scan-zoom";
var SCAN_ZOOM_LEVELS = [1, 2, 3];
var SCAN_DEFAULT_ZOOM = 2;

// Per-browser scanner preferences; storage can be unavailable (private mode).
function loadScanPref(key) {
  try {
    return window.localStorage.getItem(key) || "";
  } catch (e) {
    return "";
  }
}

function saveScanPref(key, value) {
  try {
    if (value) {
      window.localStorage.setItem(key, value);
    } else {
      window.localStorage.removeItem(key);
    }
  } catch (e) {
    // Preference is only a convenience.
  }
}

function scanVideoConstraints() {
  // A high resolution keeps small labels readable; the saved camera wins over
  // "any rear camera", which on multi-camera phones is often the wide-angle one.
  var constraints = { width: { ideal: 1920 }, height: { ideal: 1080 } };
  var deviceId = loadScanPref(SCAN_CAMERA_KEY);
  if (deviceId) {
    constraints.deviceId = { exact: deviceId };
  } else {
    constraints.facingMode = { ideal: "environment" };
  }
  return constraints;
}

function openScanStream() {
  return navigator.mediaDevices
    .getUserMedia({ video: scanVideoConstraints(), audio: false })
    .catch(function (err) {
      if (!loadScanPref(SCAN_CAMERA_KEY)) {
        throw err;
      }
      // The saved camera is gone; forget it and fall back to any rear camera.
      saveScanPref(SCAN_CAMERA_KEY, "");
      return openScanStream();
    });
}

function scanLookupUrl() {
  return document.body.getAttribute("data-scan-lookup") || "";
}

function lookupScannedCode(raw, onHit, onMiss) {
  var url = scanLookupUrl();
  if (!url) {
    onMiss();
    return;
  }
  // GET, so no CSRF token needed — and none is readable, see the file header.
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
  var video = opts.video || document.getElementById(opts.videoId);
  var startBtn = opts.startBtn || document.getElementById(opts.startId);
  var stopBtn = opts.stopBtn || document.getElementById(opts.stopId);
  var statusEl = opts.statusId ? document.getElementById(opts.statusId) : null;
  if (!video || !startBtn) {
    return null;
  }
  var stage = video.closest(".stocktake-camera");
  if (!cameraScanSupported()) {
    if (statusEl) {
      statusEl.textContent = cameraScanUnsupportedText();
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
  var controls = null;

  function cameraButton(text, onClick) {
    var btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = text;
    btn.addEventListener("click", onClick);
    return btn;
  }

  function applyZoom(track, zoom, buttons) {
    track.applyConstraints({ advanced: [{ zoom: zoom }] }).catch(function () {});
    buttons.forEach(function (btn) {
      btn.setAttribute("aria-pressed", btn._zoom === zoom ? "true" : "false");
    });
  }

  function setupTrack(track) {
    if (controls) {
      controls.remove();
      controls = null;
    }
    if (!track || !stage) {
      return;
    }
    var caps = track.getCapabilities ? track.getCapabilities() : {};
    if (caps.focusMode && caps.focusMode.indexOf("continuous") !== -1) {
      track.applyConstraints({ advanced: [{ focusMode: "continuous" }] }).catch(function () {});
    }
    controls = document.createElement("div");
    controls.className = "camera-controls";
    var zoomButtons = [];
    if (caps.zoom && caps.zoom.max > caps.zoom.min) {
      var levels = SCAN_ZOOM_LEVELS.filter(function (z) {
        return z >= caps.zoom.min && z <= caps.zoom.max;
      });
      var saved = parseFloat(loadScanPref(SCAN_ZOOM_KEY));
      var initial = levels.indexOf(saved) !== -1 ? saved : SCAN_DEFAULT_ZOOM;
      if (levels.length > 1) {
        levels.forEach(function (z) {
          var btn = cameraButton(z + "×", function () {
            saveScanPref(SCAN_ZOOM_KEY, String(z));
            applyZoom(track, z, zoomButtons);
          });
          btn._zoom = z;
          btn.setAttribute("aria-label", "Zoom " + z + "×");
          zoomButtons.push(btn);
          controls.appendChild(btn);
        });
        if (levels.indexOf(initial) === -1) {
          initial = levels[levels.length - 1];
        }
        applyZoom(track, initial, zoomButtons);
      }
    }
    var currentId = (track.getSettings && track.getSettings().deviceId) || "";
    navigator.mediaDevices
      .enumerateDevices()
      .then(function (devices) {
        var cams = devices.filter(function (d) {
          return d.kind === "videoinput" && d.deviceId;
        });
        var rear = cams.filter(function (d) {
          return /back|rear|environment/i.test(d.label);
        });
        if (rear.length > 1) {
          cams = rear;
        }
        if (cams.length < 2 || !controls) {
          return;
        }
        var index = Math.max(
          0,
          cams.findIndex(function (d) {
            return d.deviceId === currentId;
          })
        );
        var btn = cameraButton("Camera " + (index + 1) + "/" + cams.length, function () {
          var next = cams[(index + 1) % cams.length];
          saveScanPref(SCAN_CAMERA_KEY, next.deviceId);
          switchCamera();
        });
        btn.setAttribute("aria-label", "Switch camera");
        controls.appendChild(btn);
      })
      .catch(function () {});
    stage.appendChild(controls);
  }

  function attach(media) {
    stream = media;
    video.srcObject = media;
    setLive(true);
    setupTrack(media.getVideoTracks()[0]);
  }

  function switchCamera() {
    if (stream) {
      stream.getTracks().forEach(function (track) {
        track.stop();
      });
      stream = null;
    }
    openScanStream().then(attach).catch(stop);
  }

  function setLive(on) {
    if (stage) {
      stage.classList.toggle("is-live", on);
      if (stage.hasAttribute("data-hide-idle")) {
        stage.hidden = !on;
      }
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
        if (!opts.onHit) {
          goTo(data);
        } else if (opts.onHit(data)) {
          stop();
        } else {
          inflight = false;
        }
      },
      function () {
        inflight = false;
        if (opts.onMiss) {
          opts.onMiss();
        }
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
    openScanStream()
      .then(function (media) {
        attach(media);
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

var PHOTO_JPEG_QUALITIES = [0.92, 0.85, 0.75, 0.65];
var PHOTO_MIN_DIMENSION = 800;

function formatMegabytes(bytes) {
  return (bytes / (1024 * 1024)).toFixed(1).replace(/\.0$/, "") + " MB";
}

function canvasToJpeg(canvas, quality) {
  return new Promise(function (resolve, reject) {
    canvas.toBlob(
      function (blob) {
        if (blob) {
          resolve(blob);
        } else {
          reject(new Error("JPEG encoding failed"));
        }
      },
      "image/jpeg",
      quality
    );
  });
}

// Re-encode a photo as JPEG until it fits maxBytes: first lower the quality,
// then the resolution. Resolves {blob, width, height}.
function reducePhoto(file, maxBytes, maxDim) {
  return createImageBitmap(file, { imageOrientation: "from-image" }).then(function (bitmap) {
    function attempt(scale) {
      var width = Math.round(bitmap.width * scale);
      var height = Math.round(bitmap.height * scale);
      var canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      var ctx = canvas.getContext("2d");
      ctx.fillStyle = "#fff";
      ctx.fillRect(0, 0, width, height);
      ctx.drawImage(bitmap, 0, 0, width, height);

      function tryQuality(index) {
        return canvasToJpeg(canvas, PHOTO_JPEG_QUALITIES[index]).then(function (blob) {
          if (blob.size <= maxBytes) {
            return { blob: blob, width: width, height: height };
          }
          if (index + 1 < PHOTO_JPEG_QUALITIES.length) {
            return tryQuality(index + 1);
          }
          if (Math.max(width, height) <= PHOTO_MIN_DIMENSION) {
            throw new Error("photo does not fit");
          }
          return attempt(scale * 0.8);
        });
      }
      return tryQuality(0);
    }
    var first = Math.min(1, maxDim / Math.max(bitmap.width, bitmap.height));
    return attempt(first).finally(function () {
      bitmap.close();
    });
  });
}

function blobToDataUrl(blob) {
  // data: rather than blob: URLs, which the CSP (img-src 'self' data:) blocks.
  return new Promise(function (resolve, reject) {
    var reader = new FileReader();
    reader.onload = function () {
      resolve(reader.result);
    };
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

function confirmReducedPhoto(original, result, maxBytes) {
  return blobToDataUrl(result.blob).then(function (url) {
    return new Promise(function (resolve) {
      var dialog = document.createElement("dialog");
      dialog.className = "ost-dialog";
      var form = document.createElement("form");
      form.method = "dialog";
      var title = document.createElement("h2");
      title.textContent = "Photo reduced";
      var text = document.createElement("p");
      text.className = "muted";
      text.textContent =
        "The photo was " + formatMegabytes(original.size) + ", more than the " +
        formatMegabytes(maxBytes) + " limit. It was reduced to " +
        formatMegabytes(result.blob.size) + " (" + result.width + " × " + result.height +
        " px). Check the quality before saving.";
      var img = document.createElement("img");
      img.className = "photo-preview";
      img.alt = "Reduced photo";
      img.src = url;
      var actions = document.createElement("p");
      actions.className = "actions-row";
      var useBtn = document.createElement("button");
      useBtn.value = "use";
      useBtn.textContent = "Use photo";
      var cancelBtn = document.createElement("button");
      cancelBtn.value = "cancel";
      cancelBtn.className = "outline secondary";
      cancelBtn.textContent = "Cancel";
      actions.append(useBtn, cancelBtn);
      form.append(title, text, img, actions);
      dialog.appendChild(form);
      dialog.addEventListener("close", function () {
        dialog.remove();
        resolve(dialog.returnValue === "use");
      });
      document.body.appendChild(dialog);
      dialog.showModal();
    });
  });
}

function bindPhotoCapture() {
  document.addEventListener("change", function (event) {
    var input = event.target.closest("input[type='file'][data-photo-max-bytes]");
    if (!input || !input.files || !input.files.length) {
      return;
    }
    // On the item page, choosing a photo saves it at once; in forms it waits for Save.
    var form = input.closest(".js-photo-capture") ? input.form : null;
    if (form) {
      var message = form.getAttribute("data-confirm");
      if (message && !window.confirm(message)) {
        input.value = "";
        return;
      }
    }
    function submit() {
      if (!form) {
        return;
      }
      if (form.requestSubmit) {
        form.requestSubmit();
      } else {
        form.submit();
      }
    }
    var file = input.files[0];
    var maxBytes = parseInt(input.getAttribute("data-photo-max-bytes"), 10) || 0;
    var maxDim = parseInt(input.getAttribute("data-photo-max-dim"), 10) || 4096;
    if (!maxBytes || file.size <= maxBytes || !window.createImageBitmap || !window.DataTransfer) {
      submit();
      return;
    }
    reducePhoto(file, maxBytes, maxDim)
      .then(function (result) {
        return confirmReducedPhoto(file, result, maxBytes).then(function (accepted) {
          if (!accepted) {
            input.value = "";
            return;
          }
          var name = (file.name || "photo").replace(/\.[^.]*$/, "") + ".jpg";
          var transfer = new DataTransfer();
          transfer.items.add(new File([result.blob], name, { type: "image/jpeg" }));
          input.files = transfer.files;
          submit();
        });
      })
      .catch(function () {
        input.value = "";
        window.alert(
          "This photo could not be reduced below " + formatMegabytes(maxBytes) +
          ". Choose a smaller photo."
        );
      });
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
    var scanStatus = picker.querySelector("[data-host-scan-status]");

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

    function sayScan(text) {
      if (scanStatus) {
        scanStatus.textContent = text;
        scanStatus.hidden = !text;
      }
    }

    var scanBtn = picker.querySelector("[data-host-scan]");
    if (scanBtn && !cameraScanSupported()) {
      scanBtn.hidden = false;
      scanBtn.addEventListener("click", function () {
        sayScan(cameraScanUnsupportedText());
      });
    } else if (scanBtn) {
      var stopScan = bindVideoScanner({
        video: picker.querySelector("[data-host-camera] video"),
        startBtn: scanBtn,
        stopBtn: picker.querySelector("[data-host-scan-stop]"),
        onHit: function (data) {
          if (data.kind !== "item" || !data.id) {
            sayScan("That is a location label. Scan an item label.");
            return false;
          }
          if (String(data.id) === exclude) {
            sayScan("That is this item itself. Scan another label.");
            return false;
          }
          setHost(data.id, data.label);
          sayScan("Selected " + data.label + ".");
          return true;
        },
        onMiss: function () {
          sayScan("No matching item. Try another label.");
        },
      });
      if (stopScan) {
        scanBtn.hidden = false;
        scanBtn.addEventListener("click", function () {
          sayScan("");
        });
        var dialog = picker.closest("dialog");
        if (dialog) {
          dialog.addEventListener("close", stopScan);
        }
      }
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
        // GET, so no CSRF token needed — and none is readable, see the file header.
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

function bindCategoryPicker() {
  var root = document.querySelector("[data-category-picker]");
  if (!root) {
    return;
  }
  var limit = parseInt(root.getAttribute("data-category-limit") || "4", 10);
  var filter = root.querySelector("[data-category-filter]");
  var labels = root.querySelectorAll("[data-category-filter-text]");
  var boxes = root.querySelectorAll('input[name="category_pick"]');
  var typed = root.querySelectorAll(".category-slots input");
  var countEl = root.querySelector("[data-category-count]");
  var note = root.querySelector("[data-category-limit-note]");

  function uniqueNames() {
    var names = [];
    var seen = {};
    function add(raw) {
      var key = (raw || "").trim().toLowerCase();
      if (!key || seen[key]) {
        return;
      }
      seen[key] = true;
      names.push(key);
    }
    boxes.forEach(function (box) {
      if (box.checked) {
        add(box.value);
      }
    });
    typed.forEach(function (input) {
      add(input.value);
    });
    return names;
  }

  function updateCount() {
    var n = uniqueNames().length;
    if (countEl) {
      countEl.textContent = n + " / " + limit;
    }
    if (!note) {
      return;
    }
    if (n > limit) {
      note.hidden = false;
      note.textContent = "At most four categories are allowed.";
      note.classList.add("is-warn");
      return;
    }
    if (n === limit) {
      note.hidden = false;
      if (!note.classList.contains("is-warn")) {
        note.textContent = "Maximum of four selected.";
      }
      return;
    }
    note.hidden = true;
    note.classList.remove("is-warn");
    note.textContent = "";
  }

  boxes.forEach(function (box) {
    box.addEventListener("change", function () {
      if (box.checked && uniqueNames().length > limit) {
        box.checked = false;
        if (note) {
          note.hidden = false;
          note.textContent = "At most four categories are allowed.";
          note.classList.add("is-warn");
        }
      }
      updateCount();
    });
  });
  typed.forEach(function (input) {
    input.addEventListener("input", updateCount);
  });

  if (filter && labels.length) {
    filter.addEventListener("keydown", function (event) {
      if (event.key === "Enter") {
        event.preventDefault();
      }
    });
    filter.addEventListener("input", function () {
      var q = (filter.value || "").trim().toLowerCase();
      labels.forEach(function (label) {
        var text = (label.getAttribute("data-category-filter-text") || "").toLowerCase();
        label.hidden = Boolean(q) && text.indexOf(q) === -1;
      });
    });
  }
  updateCount();
}

function bindUi() {
  bindLabelFilters();
  bindNavDrawer();
  bindRoomPlaceSelects();
  bindItemHostPickers();
  bindCategoryPicker();
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
