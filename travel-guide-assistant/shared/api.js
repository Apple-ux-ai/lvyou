/** Shared TravelMate API client. */
(function () {
  'use strict';

  var utils = (window.TravelMate && window.TravelMate.utils) || {};
  var API_BASE = utils.API_BASE || 'http://127.0.0.1:8000';

  function chatStream(message, handlers, history, sessionId) {
    var h = handlers || {};
    var body = {
      message: message,
      history: history || [],
      session_id: sessionId || null
    };
    var requestOptions = {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    };
    if (h.signal) requestOptions.signal = h.signal;

    return fetch(API_BASE + '/api/chat', requestOptions)
      .then(function (resp) {
        if (!resp.ok) {
          if (resp.status === 429 && typeof resp.json === 'function') {
            return resp.json().then(function (payload) {
              var error = new Error(
                payload && payload.message
                  ? payload.message
                  : '请求太频繁，请稍后再试。'
              );
              error.code = (payload && payload.code) || 'rate_limited';
              if (payload && payload.retry_after !== undefined) {
                error.retry_after = payload.retry_after;
              }
              throw error;
            });
          }
          throw new Error('HTTP ' + resp.status);
        }
        if (!resp.body) throw new Error('Response body not readable');
        var reader = resp.body.getReader();
        var decoder = new TextDecoder('utf-8');
        var buffer = '';
        var eventName = null;

        function consumeLine(line) {
          if (line.startsWith(':')) return;
          if (line.startsWith('event:')) {
            eventName = line.slice(6).trim();
          } else if (line.startsWith('data:')) {
            var payload = parseJSON(line.slice(5).trim());
            if (payload === null) {
              eventName = null;
              return;
            }
            dispatch(eventName, payload, h);
            eventName = null;
          }
        }

        function pump() {
          return reader.read().then(function (result) {
            if (result.done) {
              buffer += decoder.decode();
              if (buffer) consumeLine(buffer);
              if (h.onComplete) h.onComplete();
              return;
            }
            buffer += decoder.decode(result.value, { stream: true });
            var lines = buffer.split('\n');
            buffer = lines.pop();

            lines.forEach(function (line) {
              consumeLine(line.replace(/\r$/, ''));
            });
            return pump();
          });
        }

        return pump();
      })
      .catch(function (err) {
        if (err && err.name === 'AbortError') {
          if (h.onAbort) h.onAbort();
          return;
        }
        if (h.onError) {
          if (err && err.code) {
            var errorPayload = { code: err.code, message: err.message || String(err) };
            if (err.retry_after !== undefined) errorPayload.retry_after = err.retry_after;
            h.onError(errorPayload);
            return;
          }
          h.onError({ code: 'network_error', message: err.message || String(err) });
        }
      });
  }

  function dispatch(eventName, payload, handlers) {
    switch (eventName) {
      case 'message':
        if (handlers.onMessage) handlers.onMessage(payload);
        break;
      case 'itinerary':
        if (handlers.onItinerary) handlers.onItinerary(payload);
        break;
      case 'done':
        if (handlers.onDone) handlers.onDone(payload);
        break;
      case 'error':
        if (handlers.onError) handlers.onError(payload);
        break;
      default:
        break;
    }
  }

  function parseJSON(text) {
    try { return JSON.parse(text); } catch (e) { return null; }
  }

  function requestJSON(url, options, onOk, onError) {
    fetch(url, options)
      .then(function (resp) {
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        return resp.json();
      })
      .then(function (payload) {
        if (onOk) onOk(payload);
      })
      .catch(function (err) {
        if (onError) onError(err);
      });
  }

  function saveTrip(itinerary, onOk, onError) {
    requestJSON(API_BASE + '/api/trips', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(itinerary)
    }, onOk, onError);
  }

  function getTrip(id, onOk, onError) {
    requestJSON(API_BASE + '/api/trips/' + encodeURIComponent(id), undefined, onOk, onError);
  }

  function listTrips(onOk, onError) {
    requestJSON(API_BASE + '/api/trips', undefined, onOk, onError);
  }

  function updateTrip(id, itinerary, onOk, onError) {
    requestJSON(API_BASE + '/api/trips/' + encodeURIComponent(id), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(itinerary)
    }, onOk, onError);
  }

  window.TravelMate = window.TravelMate || {};
  window.TravelMate.api = {
    chatStream: chatStream,
    saveTrip: saveTrip,
    getTrip: getTrip,
    listTrips: listTrips,
    updateTrip: updateTrip
  };
})();
