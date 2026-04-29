package dt

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
)

func TestClientGetAndRetry(t *testing.T) {
	var calls atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		n := calls.Add(1)
		if r.Header.Get("Authorization") != "Bearer t-1" {
			t.Errorf("auth header: got %q", r.Header.Get("Authorization"))
		}
		if n == 1 {
			w.WriteHeader(http.StatusServiceUnavailable)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"id":"d1","name":"docs-helper","type":"dtguard.attestation","content":{"ok":true}}`))
	}))
	defer srv.Close()

	c := New(srv.URL, "t-1")
	doc, err := c.Get(context.Background(), "d1")
	if err != nil {
		t.Fatalf("Get: %v", err)
	}
	if calls.Load() != 2 {
		t.Errorf("calls: want 2 (one retry), got %d", calls.Load())
	}
	if doc.Name != "docs-helper" || string(doc.Content) != `{"ok":true}` {
		t.Errorf("doc decode: %+v", doc)
	}
}

func TestClientStructuredError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("X-Request-Id", "req-42")
		w.WriteHeader(http.StatusForbidden)
		_, _ = w.Write([]byte(`{"error":{"code":"FORBIDDEN","message":"insufficient scope","suggestions":["grant document:write"]}}`))
	}))
	defer srv.Close()

	c := New(srv.URL, "t-1")
	_, err := c.Get(context.Background(), "d1")
	var dterr *Error
	if !errors.As(err, &dterr) {
		t.Fatalf("want *Error, got %T: %v", err, err)
	}
	if dterr.StatusCode != 403 || dterr.Code != "FORBIDDEN" || dterr.RequestID != "req-42" {
		t.Errorf("error fields: %+v", dterr)
	}
	if len(dterr.Suggestions) != 1 || dterr.Suggestions[0] != "grant document:write" {
		t.Errorf("suggestions: %v", dterr.Suggestions)
	}
}
