// Package dt is the HTTP client for the Dynatrace Documents API. dtguard
// stores its custom resources (attestations, proposals, etc.) as documents
// keyed by name; the wire body is the JSON-encoded resource.
package dt

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

// Document is the on-the-wire shape returned by the Documents API.
// Content is the opaque resource body owned by the caller.
type Document struct {
	ID       string          `json:"id,omitempty"`
	Name     string          `json:"name"`
	Type     string          `json:"type"`
	Owner    string          `json:"owner,omitempty"`
	Version  int             `json:"version,omitempty"`
	Modified time.Time       `json:"modificationTime,omitempty"`
	Content  json.RawMessage `json:"content"`
}

// Error is the structured failure returned by every Client method.
type Error struct {
	StatusCode  int
	Code        string
	Message     string
	RequestID   string
	Suggestions []string
}

func (e *Error) Error() string {
	if e.Code != "" {
		return fmt.Sprintf("dt api: %d %s: %s", e.StatusCode, e.Code, e.Message)
	}
	return fmt.Sprintf("dt api: %d: %s", e.StatusCode, e.Message)
}

// Client talks to the Documents API at TenantURL/platform/document/v1.
type Client struct {
	tenant string
	token  string
	http   *http.Client
	// retries is the number of additional attempts on 5xx/429. Default 2.
	retries int
}

// New builds a client. tenant must be the bare environment URL.
func New(tenant, token string) *Client {
	return &Client{
		tenant:  strings.TrimRight(tenant, "/"),
		token:   token,
		http:    &http.Client{Timeout: 30 * time.Second},
		retries: 2,
	}
}

const docPath = "/platform/document/v1/documents"

// Get fetches a single document by ID.
func (c *Client) Get(ctx context.Context, id string) (*Document, error) {
	var out Document
	if err := c.do(ctx, http.MethodGet, docPath+"/"+url.PathEscape(id), nil, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// List returns documents of the given type. typeFilter may be empty.
func (c *Client) List(ctx context.Context, typeFilter string) ([]Document, error) {
	q := ""
	if typeFilter != "" {
		q = "?filter=" + url.QueryEscape(fmt.Sprintf(`type=='%s'`, typeFilter))
	}
	var out struct {
		Documents []Document `json:"documents"`
	}
	if err := c.do(ctx, http.MethodGet, docPath+q, nil, &out); err != nil {
		return nil, err
	}
	return out.Documents, nil
}

// Apply upserts a document. If doc.ID is set, the existing document is
// updated; otherwise a new document is created.
func (c *Client) Apply(ctx context.Context, doc *Document) (*Document, error) {
	var (
		method = http.MethodPost
		path   = docPath
	)
	if doc.ID != "" {
		method = http.MethodPut
		path = docPath + "/" + url.PathEscape(doc.ID)
	}
	var out Document
	if err := c.do(ctx, method, path, doc, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// Delete removes a document by ID. A 404 is reported as a *Error so callers
// can treat "already gone" as non-fatal if they want.
func (c *Client) Delete(ctx context.Context, id string) error {
	return c.do(ctx, http.MethodDelete, docPath+"/"+url.PathEscape(id), nil, nil)
}

// do executes an HTTP request with retry on 5xx/429 and decodes the
// response into out (if non-nil).
func (c *Client) do(ctx context.Context, method, path string, body, out any) error {
	var encoded []byte
	if body != nil {
		var err error
		encoded, err = json.Marshal(body)
		if err != nil {
			return fmt.Errorf("marshal request: %w", err)
		}
	}

	var lastErr error
	for attempt := 0; attempt <= c.retries; attempt++ {
		if err := backoff(ctx, attempt); err != nil {
			return err
		}
		err := c.attempt(ctx, method, path, encoded, body != nil, out)
		if err == nil {
			return nil
		}
		var dterr *Error
		if errors.As(err, &dterr) && retryable(dterr.StatusCode) {
			lastErr = err
			continue
		}
		if dterr == nil {
			lastErr = err
			continue
		}
		return err
	}
	return lastErr
}

func (c *Client) attempt(ctx context.Context, method, path string, encoded []byte, hasBody bool, out any) error {
	req, err := http.NewRequestWithContext(ctx, method, c.tenant+path, bytes.NewReader(encoded))
	if err != nil {
		return fmt.Errorf("build request: %w", err)
	}
	req.Header.Set("Authorization", "Bearer "+c.token)
	req.Header.Set("Accept", "application/json")
	if hasBody {
		req.Header.Set("Content-Type", "application/json")
	}
	resp, err := c.http.Do(req)
	if err != nil {
		return fmt.Errorf("%s %s: %w", method, path, err)
	}
	defer resp.Body.Close()
	return handle(resp, out)
}

func backoff(ctx context.Context, attempt int) error {
	if attempt == 0 {
		return nil
	}
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-time.After(time.Duration(1<<attempt) * 200 * time.Millisecond):
		return nil
	}
}

func handle(resp *http.Response, out any) error {
	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode >= 400 {
		return decodeError(resp, body)
	}
	if out == nil || len(body) == 0 {
		return nil
	}
	if err := json.Unmarshal(body, out); err != nil {
		return fmt.Errorf("decode response: %w", err)
	}
	return nil
}

func decodeError(resp *http.Response, body []byte) error {
	e := &Error{
		StatusCode: resp.StatusCode,
		RequestID:  resp.Header.Get("X-Request-Id"),
		Message:    strings.TrimSpace(string(body)),
	}
	var wire struct {
		Error struct {
			Code        string   `json:"code"`
			Message     string   `json:"message"`
			Suggestions []string `json:"suggestions"`
		} `json:"error"`
	}
	if json.Unmarshal(body, &wire) == nil && wire.Error.Message != "" {
		e.Code = wire.Error.Code
		e.Message = wire.Error.Message
		e.Suggestions = wire.Error.Suggestions
	}
	if e.Message == "" {
		e.Message = resp.Status
	}
	return e
}

func retryable(status int) bool {
	return status == http.StatusTooManyRequests || (status >= 500 && status <= 599)
}
