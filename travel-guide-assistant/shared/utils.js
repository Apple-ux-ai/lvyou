/**
 * TravelMate 共享工具函数（Phase 0）
 * 全局注入于 window.TravelMate.utils，供所有页面使用
 */
(function () {
  'use strict';

  var API_BASE = (typeof window.TravelMateConfig !== 'undefined' && window.TravelMateConfig.API_BASE)
    ? window.TravelMateConfig.API_BASE
    : 'http://127.0.0.1:8000';

  var THEME_KEY = 'travelmate-theme';

  /** 主题切换 */
  function getTheme() {
    return document.documentElement.classList.contains('dark') ? 'dark' : 'light';
  }

  function setTheme(theme) {
    if (theme === 'dark') {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
    try { localStorage.setItem(THEME_KEY, theme); } catch (e) { /* ignore */ }
  }

  function toggleTheme() {
    var next = getTheme() === 'dark' ? 'light' : 'dark';
    setTheme(next);
    return next;
  }

  function initTheme() {
    var saved = null;
    try { saved = localStorage.getItem(THEME_KEY); } catch (e) { /* ignore */ }
    setTheme(saved === 'dark' ? 'dark' : 'light');
  }

  /** 路由跳转 */
  function go(page, params) {
    var url = page;
    if (params) {
      var qs = Object.keys(params)
        .filter(function (k) { return params[k] !== undefined && params[k] !== null; })
        .map(function (k) { return encodeURIComponent(k) + '=' + encodeURIComponent(params[k]); })
        .join('&');
      if (qs) url += '?' + qs;
    }
    window.location.href = url;
  }

  function withQueryParams(params) {
    var qs = Object.keys(params)
      .filter(function (k) { return params[k] !== undefined && params[k] !== null; })
      .map(function (k) { return encodeURIComponent(k) + '=' + encodeURIComponent(params[k]); })
      .join('&');
    return qs ? '?' + qs : '';
  }

  /** 读取 URL 查询参数 */
  function getQueryParam(name) {
    return new URLSearchParams(window.location.search).get(name);
  }

  /* ── Auth 会话（Phase 3，localStorage 游客/邮箱模式） ── */
  var SESSION_KEY = 'travelmate-user';

  function getSession() {
    try {
      var raw = localStorage.getItem(SESSION_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (e) { return null; }
  }

  function setSession(user) {
    try { localStorage.setItem(SESSION_KEY, JSON.stringify(user)); } catch (e) { /* ignore */ }
  }

  function clearSession() {
    try { localStorage.removeItem(SESSION_KEY); } catch (e) { /* ignore */ }
  }

  function isLoggedIn() {
    var u = getSession();
    return !!(u && u.name);
  }

  function makeGuest() {
    setSession({ name: '游客', email: null, isGuest: true, joinedAt: new Date().toISOString() });
    return getSession();
  }

  window.TravelMate = window.TravelMate || {};
  window.TravelMate.utils = {
    API_BASE: API_BASE,
    getTheme: getTheme,
    setTheme: setTheme,
    toggleTheme: toggleTheme,
    initTheme: initTheme,
    go: go,
    withQueryParams: withQueryParams,
    getQueryParam: getQueryParam,
    getSession: getSession,
    setSession: setSession,
    clearSession: clearSession,
    isLoggedIn: isLoggedIn,
    makeGuest: makeGuest
  };
})();
