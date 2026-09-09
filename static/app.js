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
  var desktop = window.matchMedia("(min-width: 45rem)");
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

function bindSharePng() {
  document.addEventListener("click", function (event) {
    var btn = event.target.closest("[data-share-png]");
    if (!btn) {
      return;
    }
    event.preventDefault();
    var uri = btn.getAttribute("data-share-png");
    var name = btn.getAttribute("data-share-name") || "label.png";
    if (!navigator.share || !navigator.canShare) {
      btn.textContent = "Use Download PNG";
      return;
    }
    fetch(uri)
      .then(function (res) {
        return res.blob();
      })
      .then(function (blob) {
        var file = new File([blob], name, { type: "image/png" });
        if (!navigator.canShare({ files: [file] })) {
          btn.textContent = "Use Download PNG";
          return;
        }
        return navigator.share({ files: [file], title: name });
      })
      .catch(function (err) {
        if (err && err.name === "AbortError") {
          return;
        }
        btn.textContent = "Use Download PNG";
      });
  });
}

function bindStocktakeCamera() {
  var video = document.getElementById("stocktake-video");
  var startBtn = document.getElementById("stocktake-camera-start");
  var stopBtn = document.getElementById("stocktake-camera-stop");
  if (!video || !startBtn) {
    return;
  }
  if (!("BarcodeDetector" in window) || !navigator.mediaDevices) {
    return;
  }
  startBtn.hidden = false;
  var stream = null;
  var timer = null;
  var detector = new BarcodeDetector({ formats: ["qr_code"] });
  var going = false;

  function stop() {
    going = false;
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
    video.hidden = true;
    stopBtn.hidden = true;
    startBtn.hidden = false;
  }

  function handleValue(raw) {
    try {
      var parsed = new URL(raw, window.location.origin);
      if (parsed.origin !== window.location.origin) {
        return false;
      }
      if (/^\/i\/\d+\/$/.test(parsed.pathname) || /^\/l\/\d+\/$/.test(parsed.pathname)) {
        stop();
        window.location.href = parsed.pathname;
        return true;
      }
    } catch (e) {
      return false;
    }
    return false;
  }

  function tick() {
    if (!going || video.readyState < 2) {
      timer = window.setTimeout(tick, 250);
      return;
    }
    detector
      .detect(video)
      .then(function (codes) {
        var i;
        for (i = 0; i < codes.length; i += 1) {
          if (handleValue(codes[i].rawValue || "")) {
            return;
          }
        }
        timer = window.setTimeout(tick, 250);
      })
      .catch(function () {
        timer = window.setTimeout(tick, 400);
      });
  }

  startBtn.addEventListener("click", function () {
    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: "environment" }, audio: false })
      .then(function (media) {
        stream = media;
        video.srcObject = media;
        video.hidden = false;
        startBtn.hidden = true;
        stopBtn.hidden = false;
        going = true;
        tick();
      })
      .catch(function () {
        startBtn.textContent = "Camera unavailable";
      });
  });
  if (stopBtn) {
    stopBtn.addEventListener("click", stop);
  }
}

function bindUi() {
  bindLabelFilters();
  bindNavDrawer();
  bindRoomPlaceSelects();
  bindSharePng();
  bindStocktakeCamera();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", bindUi);
} else {
  bindUi();
}
