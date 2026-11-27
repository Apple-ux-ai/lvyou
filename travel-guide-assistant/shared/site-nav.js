(function () {
  "use strict";

  var items = [
    { id: "home", label: "首页", href: "home.html" },
    { id: "destination", label: "目的地", href: "explore.html" },
    { id: "guides", label: "攻略", href: "guides.html" },
    { id: "community", label: "社区", href: "community.html" }
  ];

  var page = (window.location.pathname.split("/").pop() || "home.html").toLowerCase();
  var activeId = page === "home.html" ? "home"
    : ["explore.html", "destination.html", "compare.html"].indexOf(page) >= 0 ? "destination"
      : ["guides.html", "guide-detail.html"].indexOf(page) >= 0 ? "guides"
        : page === "community.html" ? "community" : "";

  function linkMarkup(className) {
    return items.map(function (item) {
      var active = item.id === activeId ? " active" : "";
      return '<a class="' + className + active + '" href="' + item.href + '"' + (active ? ' aria-current="page"' : '') + '>' + item.label + '</a>';
    }).join("");
  }

  function isExpectedNav(nav, className) {
    var links = Array.prototype.slice.call(nav.querySelectorAll("a"));
    return links.length === items.length && links.every(function (link, index) {
      var item = items[index];
      return link.getAttribute("href") === item.href
        && link.textContent.trim() === item.label
        && link.classList.contains(className)
        && (item.id === activeId ? link.classList.contains("active") : !link.classList.contains("active"));
    });
  }

  function normalizeNav(nav, className) {
    nav.classList.add("tm-shared-nav");
    if (isExpectedNav(nav, className)) return;
    nav.innerHTML = linkMarkup(className);
  }

  function ensureMobileNav(topbar) {
    var mobileNav = topbar.querySelector(".mobile-nav");
    var menuButton = topbar.querySelector(".menu-btn, .mobile-menu-btn, .tm-nav-toggle");

    if (mobileNav) {
      mobileNav.classList.add("tm-shared-mobile-nav");
      normalizeNav(mobileNav, "mobile-nav-link");
    }

    if (menuButton) return;

    menuButton = document.createElement("button");
    menuButton.type = "button";
    menuButton.className = "icon-btn tm-nav-toggle";
    menuButton.title = "打开菜单";
    menuButton.setAttribute("aria-label", "打开菜单");
    menuButton.setAttribute("aria-expanded", "false");
    menuButton.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 6h16M4 12h16M4 18h16"/></svg>';
    var right = topbar.querySelector(".topbar-right");
    if (right) right.insertBefore(menuButton, right.firstChild);

    mobileNav = document.createElement("nav");
    mobileNav.className = "mobile-nav tm-shared-mobile-nav";
    mobileNav.hidden = true;
    mobileNav.innerHTML = linkMarkup("mobile-nav-link");
    topbar.appendChild(mobileNav);

    menuButton.addEventListener("click", function () {
      var open = topbar.classList.toggle("tm-nav-open");
      mobileNav.hidden = !open;
      menuButton.setAttribute("aria-expanded", String(open));
    });
  }

  function ensureAvatar(topbar) {
    var avatar = topbar.querySelector(".avatar");
    if (!avatar) {
      if (topbar.querySelector(".tm-profile-link, .tm-profile-text")) return;
      var right = topbar.querySelector(".topbar-right");
      if (!right) return;
      var profileText = document.createElement("a");
      profileText.className = "tm-profile-text";
      profileText.href = "profile.html";
      profileText.textContent = "个人中心";
      right.appendChild(profileText);
      return;
    }
    if (avatar.parentElement && avatar.parentElement.matches("a")) return;
    var profileLink = document.createElement("a");
    profileLink.className = "tm-profile-link";
    profileLink.href = "profile.html";
    profileLink.setAttribute("aria-label", "个人中心");
    avatar.parentNode.insertBefore(profileLink, avatar);
    profileLink.appendChild(avatar);
  }

  function enhanceTopbar(topbar) {
    if (!topbar || topbar.dataset.tmNavReady === "true") {
      if (topbar) {
        var existingNav = topbar.querySelector(".nav-links");
        if (existingNav) normalizeNav(existingNav, "nav-link");
        ensureMobileNav(topbar);
        ensureAvatar(topbar);
      }
      return;
    }

    topbar.dataset.tmNavReady = "true";
    var left = topbar.querySelector(".topbar-left");
    var desktopNav = topbar.querySelector(".nav-links");
    if (!desktopNav && left) {
      desktopNav = document.createElement("nav");
      desktopNav.className = "nav-links";
      left.appendChild(desktopNav);
    }
    if (desktopNav) normalizeNav(desktopNav, "nav-link");
    ensureMobileNav(topbar);
    ensureAvatar(topbar);
  }

  function enhanceAll() {
    Array.prototype.forEach.call(document.querySelectorAll(".topbar"), enhanceTopbar);
  }

  function start() {
    enhanceAll();
    new MutationObserver(enhanceAll).observe(document.body, { childList: true, subtree: true });
  }

  if (document.body) start();
  else document.addEventListener("DOMContentLoaded", start, { once: true });
})();
