package main

import (
	"context"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"log"
	"math"
	"math/rand"
	"net"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"
)

// ==================== RESILIENCE MANAGER ====================

type ResilienceManager struct {
	transportStack  *TransportStack
	circuitBreaker  *CircuitBreaker
	dnsResolver     *DoHResolver
	connectionPool  *ConnectionPool
	healthChecker   *HealthChecker
	retryConfig     RetryConfig
	config          ResilienceConfig
}

type ResilienceConfig struct {
	MaxRetries          int
	BaseDelay           time.Duration
	MaxDelay            time.Duration
	HealthCheckInterval time.Duration
	HealthCheckTimeout  time.Duration
	DNSCacheTTL         time.Duration
	CircuitThreshold    int
	CircuitTimeout      time.Duration
}

func NewResilienceManager(config ResilienceConfig) *ResilienceManager {
	rm := &ResilienceManager{
		config: config,
	}
	
	// Initialize components
	rm.transportStack = NewTransportStack()
	rm.circuitBreaker = NewCircuitBreaker(config.CircuitThreshold, config.CircuitTimeout)
	rm.dnsResolver = NewDoHResolver(config.DNSCacheTTL)
	rm.connectionPool = NewConnectionPool(10, 5*time.Minute)
	rm.healthChecker = NewHealthChecker(config.HealthCheckInterval, config.HealthCheckTimeout)
	rm.retryConfig = RetryConfig{
		MaxAttempts:   config.MaxRetries,
		BaseDelay:     config.BaseDelay,
		MaxDelay:      config.MaxDelay,
		BackoffFactor: 2.0,
		JitterStrategy: FullJitter,
	}
	
	return rm
}

func (rm *ResilienceManager) Request(ctx context.Context, targetURL string) (*http.Response, error) {
	// DNS resolution with cache
	parsed, err := url.Parse(targetURL)
	if err != nil {
		return nil, fmt.Errorf("invalid URL: %w", err)
	}
	
	ips, err := rm.dnsResolver.Resolve(parsed.Host)
	if err != nil {
		log.Printf("DNS resolution failed for %s: %v", parsed.Host, err)
		// Fallback to system DNS
		ips, err = net.LookupHost(parsed.Host)
		if err != nil {
			return nil, fmt.Errorf("system DNS also failed: %w", err)
		}
	}
	
	// Circuit breaker + retry with connection pooling
	var resp *http.Response
	err = rm.circuitBreaker.Call(func() error {
		return RetryWithBackoff(func() error {
			// Create HTTP client with connection pooling
			client := &http.Client{
				Timeout: 30 * time.Second,
				Transport: &http.Transport{
					MaxIdleConns:        10,
					MaxIdleConnsPerHost: 5,
					IdleConnTimeout:     90 * time.Second,
					DialContext: func(ctx context.Context, network, addr string) (net.Conn, error) {
						// Try to use resolved IPs
						if len(ips) > 0 && addr == parsed.Host+":443" {
							addr = net.JoinHostPort(ips[0], "443")
						}
						dialer := &net.Dialer{
							Timeout:   10 * time.Second,
							KeepAlive: 30 * time.Second,
						}
						return dialer.DialContext(ctx, network, addr)
					},
				},
			}
			
			req, err := http.NewRequestWithContext(ctx, "GET", targetURL, nil)
			if err != nil {
				return err
			}
			
			resp, err = client.Do(req)
			if err != nil {
				return err
			}
			
			// Check for retryable status codes
			if resp.StatusCode >= 500 || resp.StatusCode == 429 {
				resp.Body.Close()
				return fmt.Errorf("server error: %d", resp.StatusCode)
			}
			
			return nil
		}, rm.retryConfig)
	})
	
	if err != nil {
		return nil, err
	}
	
	return resp, nil
}

// ==================== TRANSPORT STACK ====================

type TransportStack struct {
	transports []Transport
	current    int
	backoff    ExponentialBackoff
	mutex      sync.RWMutex
}

type Transport interface {
	Connect(ctx context.Context, target string) (net.Conn, error)
	Priority() int
	HealthCheck() bool
	ExecuteRequest(ctx context.Context, conn net.Conn, url string) (*http.Response, error)
	Name() string
}

type ExponentialBackoff struct {
	baseDelay time.Duration
	maxDelay  time.Duration
	factor    float64
}

func NewTransportStack() *TransportStack {
	return &TransportStack{
		transports: []Transport{
			&DirectHTTPSTransport{},
			&WebSocketTransport{},
			&HTTP2Transport{},
			&DoHTransport{},
			&TCPTunnelTransport{},
		},
		backoff: ExponentialBackoff{
			baseDelay: 1 * time.Second,
			maxDelay:  30 * time.Second,
			factor:    2.0,
		},
	}
}

func (ts *TransportStack) GetBestTransport() Transport {
	ts.mutex.RLock()
	defer ts.mutex.RUnlock()
	
	for _, transport := range ts.transports {
		if transport.HealthCheck() {
			return transport
		}
	}
	
	return ts.transports[0] // Fallback to first
}

func (ts *TransportStack) FallbackRequest(ctx context.Context, targetURL string) (*http.Response, error) {
	ts.mutex.Lock()
	defer ts.mutex.Unlock()
	
	for attempt := 0; attempt < len(ts.transports); attempt++ {
		transport := ts.transports[ts.current]
		
		log.Printf("Trying transport: %s (priority %d)", transport.Name(), transport.Priority())
		
		parsed, _ := url.Parse(targetURL)
		conn, err := transport.Connect(ctx, parsed.Host)
		if err == nil {
			resp, err := transport.ExecuteRequest(ctx, conn, targetURL)
			if err == nil {
				return resp, nil
			}
			conn.Close()
		}
		
		// Move to next transport
		ts.current = (ts.current + 1) % len(ts.transports)
		ts.backoff.Wait()
	}
	
	return nil, fmt.Errorf("all transports failed")
}

// ==================== TRANSPORT IMPLEMENTATIONS ====================

type DirectHTTPSTransport struct{}

func (t *DirectHTTPSTransport) Connect(ctx context.Context, target string) (net.Conn, error) {
	dialer := &net.Dialer{Timeout: 10 * time.Second}
	conn, err := dialer.DialContext(ctx, "tcp", target)
	if err != nil {
		return nil, err
	}
	
	// TLS handshake
	tlsConn := tls.Client(conn, &tls.Config{
		ServerName: strings.Split(target, ":")[0],
		NextProtos: []string{"h2", "http/1.1"},
	})
	
	err = tlsConn.Handshake()
	if err != nil {
		conn.Close()
		return nil, err
	}
	
	return tlsConn, nil
}

func (t *DirectHTTPSTransport) Priority() int { return 0 }
func (t *DirectHTTPSTransport) HealthCheck() bool { return true }
func (t *DirectHTTPSTransport) Name() string { return "direct_https" }

func (t *DirectHTTPSTransport) ExecuteRequest(ctx context.Context, conn net.Conn, targetURL string) (*http.Response, error) {
	req, err := http.NewRequestWithContext(ctx, "GET", targetURL, nil)
	if err != nil {
		return nil, err
	}
	
	client := &http.Client{
		Transport: &http.Transport{
			DialContext: func(ctx context.Context, network, addr string) (net.Conn, error) {
				return conn, nil
			},
		},
	}
	
	return client.Do(req)
}

type WebSocketTransport struct{}

func (t *WebSocketTransport) Connect(ctx context.Context, target string) (net.Conn, error) {
	dialer := &net.Dialer{Timeout: 10 * time.Second}
	conn, err := dialer.DialContext(ctx, "tcp", target)
	if err != nil {
		return nil, err
	}
	
	tlsConn := tls.Client(conn, &tls.Config{
		ServerName: strings.Split(target, ":")[0],
		NextProtos: []string{"http/1.1"},
	})
	
	err = tlsConn.Handshake()
	if err != nil {
		conn.Close()
		return nil, err
	}
	
	return tlsConn, nil
}

func (t *WebSocketTransport) Priority() int { return 1 }
func (t *WebSocketTransport) HealthCheck() bool { return true }
func (t *WebSocketTransport) Name() string { return "websocket" }

func (t *WebSocketTransport) ExecuteRequest(ctx context.Context, conn net.Conn, targetURL string) (*http.Response, error) {
	req, err := http.NewRequestWithContext(ctx, "GET", targetURL, nil)
	if err != nil {
		return nil, err
	}
	
	req.Header.Set("Upgrade", "websocket")
	req.Header.Set("Connection", "Upgrade")
	req.Header.Set("Sec-WebSocket-Key", "dGhlIHNhbXBsZSBub25jZQ==")
	req.Header.Set("Sec-WebSocket-Version", "13")
	
	client := &http.Client{
		Transport: &http.Transport{
			DialContext: func(ctx context.Context, network, addr string) (net.Conn, error) {
				return conn, nil
			},
		},
	}
	
	return client.Do(req)
}

type HTTP2Transport struct{}

func (t *HTTP2Transport) Connect(ctx context.Context, target string) (net.Conn, error) {
	dialer := &net.Dialer{Timeout: 10 * time.Second}
	conn, err := dialer.DialContext(ctx, "tcp", target)
	if err != nil {
		return nil, err
	}
	
	tlsConn := tls.Client(conn, &tls.Config{
		ServerName: strings.Split(target, ":")[0],
		NextProtos: []string{"h2"},
	})
	
	err = tlsConn.Handshake()
	if err != nil {
		conn.Close()
		return nil, err
	}
	
	return tlsConn, nil
}

func (t *HTTP2Transport) Priority() int { return 2 }
func (t *HTTP2Transport) HealthCheck() bool { return true }
func (t *HTTP2Transport) Name() string { return "http2" }

func (t *HTTP2Transport) ExecuteRequest(ctx context.Context, conn net.Conn, targetURL string) (*http.Response, error) {
	req, err := http.NewRequestWithContext(ctx, "GET", targetURL, nil)
	if err != nil {
		return nil, err
	}
	
	client := &http.Client{
		Transport: &http.Transport{
			DialContext: func(ctx context.Context, network, addr string) (net.Conn, error) {
				return conn, nil
			},
			ForceAttemptHTTP2: true,
		},
	}
	
	return client.Do(req)
}

type DoHTransport struct{}

func (t *DoHTransport) Connect(ctx context.Context, target string) (net.Conn, error) {
	return nil, fmt.Errorf("DoH is not a direct transport")
}

func (t *DoHTransport) Priority() int { return 3 }
func (t *DoHTransport) HealthCheck() bool { return true }
func (t *DoHTransport) Name() string { return "doh" }

func (t *DoHTransport) ExecuteRequest(ctx context.Context, conn net.Conn, targetURL string) (*http.Response, error) {
	return nil, fmt.Errorf("DoH is not a direct transport")
}

type TCPTunnelTransport struct {
	proxyURL string
}

func (t *TCPTunnelTransport) Connect(ctx context.Context, target string) (net.Conn, error) {
	if t.proxyURL == "" {
		t.proxyURL = "http://proxy.example.com:8080"
	}
	
	proxyParsed, err := url.Parse(t.proxyURL)
	if err != nil {
		return nil, err
	}
	
	dialer := &net.Dialer{Timeout: 10 * time.Second}
	conn, err := dialer.DialContext(ctx, "tcp", proxyParsed.Host)
	if err != nil {
		return nil, err
	}
	
	connectReq := fmt.Sprintf("CONNECT %s HTTP/1.1\r\nHost: %s\r\n\r\n", target, target)
	_, err = conn.Write([]byte(connectReq))
	if err != nil {
		conn.Close()
		return nil, err
	}
	
	buf := make([]byte, 1024)
	n, err := conn.Read(buf)
	if err != nil {
		conn.Close()
		return nil, err
	}
	
	response := string(buf[:n])
	if !strings.Contains(response, "200") {
		conn.Close()
		return nil, fmt.Errorf("CONNECT failed: %s", response)
	}
	
	return conn, nil
}

func (t *TCPTunnelTransport) Priority() int { return 4 }
func (t *TCPTunnelTransport) HealthCheck() bool { return true }
func (t *TCPTunnelTransport) Name() string { return "tcp_tunnel" }

func (t *TCPTunnelTransport) ExecuteRequest(ctx context.Context, conn net.Conn, targetURL string) (*http.Response, error) {
	req, err := http.NewRequestWithContext(ctx, "GET", targetURL, nil)
	if err != nil {
		return nil, err
	}
	
	client := &http.Client{
		Transport: &http.Transport{
			DialContext: func(ctx context.Context, network, addr string) (net.Conn, error) {
				return conn, nil
			},
		},
	}
	
	return client.Do(req)
}

// ==================== CIRCUIT BREAKER ====================

type State int

const (
	Closed State = iota
	Open
	HalfOpen
)

type CircuitBreaker struct {
	state        State
	failureCount int
	threshold    int
	timeout      time.Duration
	lastFailure  time.Time
	mutex        sync.RWMutex
}

func NewCircuitBreaker(threshold int, timeout time.Duration) *CircuitBreaker {
	return &CircuitBreaker{
		state:     Closed,
		threshold: threshold,
		timeout:   timeout,
	}
}

func (cb *CircuitBreaker) Call(fn func() error) error {
	cb.mutex.RLock()
	state := cb.state
	cb.mutex.RUnlock()
	
	if state == Open {
		if time.Since(cb.lastFailure) > cb.timeout {
			cb.mutex.Lock()
			cb.state = HalfOpen
			cb.mutex.Unlock()
		} else {
			return fmt.Errorf("circuit breaker is open")
		}
	}
	
	err := fn()
	
	cb.mutex.Lock()
	defer cb.mutex.Unlock()
	
	if err != nil {
		cb.failureCount++
		if cb.failureCount >= cb.threshold {
			cb.state = Open
			cb.lastFailure = time.Now()
			log.Printf("Circuit breaker opened after %d failures", cb.failureCount)
		}
		return err
	}
	
	cb.failureCount = 0
	cb.state = Closed
	return nil
}

// ==================== RETRY WITH BACKOFF ====================

type JitterType int

const (
	NoJitter JitterType = iota
	FullJitter
	EqualJitter
	DecorrelatedJitter
)

type RetryConfig struct {
	MaxAttempts    int
	BaseDelay      time.Duration
	MaxDelay       time.Duration
	BackoffFactor  float64
	JitterStrategy JitterType
}

func RetryWithBackoff(fn func() error, config RetryConfig) error {
	var lastDelay time.Duration
	
	for attempt := 0; attempt < config.MaxAttempts; attempt++ {
		err := fn()
		if err == nil {
			return nil
		}
		
		if !isRetryable(err) {
			return err
		}
		
		if attempt == config.MaxAttempts-1 {
			break
		}
		
		delay := calculateDelay(attempt, config, lastDelay)
		log.Printf("Retry attempt %d after %v", attempt+1, delay)
		time.Sleep(delay)
		lastDelay = delay
	}
	
	return fmt.Errorf("max retries (%d) exceeded", config.MaxAttempts)
}

func calculateDelay(attempt int, config RetryConfig, lastDelay time.Duration) time.Duration {
	var delay time.Duration
	
	switch config.JitterStrategy {
	case DecorrelatedJitter:
		if lastDelay == 0 {
			delay = config.BaseDelay
		} else {
			delay = time.Duration(float64(lastDelay) * 3 * rand.Float64())
		}
	default:
		exponential := time.Duration(float64(config.BaseDelay) * 
			math.Pow(config.BackoffFactor, float64(attempt)))
		delay = minDuration(exponential, config.MaxDelay)
		
		switch config.JitterStrategy {
		case FullJitter:
			delay = time.Duration(rand.Float64() * float64(delay))
		case EqualJitter:
			halfDelay := delay / 2
			delay = halfDelay + time.Duration(rand.Float64()*float64(halfDelay))
		}
	}
	
	return minDuration(delay, config.MaxDelay)
}

func isRetryable(err error) bool {
	if err == nil {
		return false
	}
	
	errStr := err.Error()
	retryableErrors := []string{
		"connection refused",
		"connection reset",
		"timeout",
		"temporary failure",
		"502",
		"503",
		"504",
		"429",
	}
	
	for _, retryable := range retryableErrors {
		if strings.Contains(strings.ToLower(errStr), retryable) {
			return true
		}
	}
	
	return false
}

func minDuration(a, b time.Duration) time.Duration {
	if a < b {
		return a
	}
	return b
}

func (eb *ExponentialBackoff) Wait() {
	delay := eb.baseDelay
	eb.baseDelay = time.Duration(float64(eb.baseDelay) * eb.factor)
	if eb.baseDelay > eb.maxDelay {
		eb.baseDelay = eb.maxDelay
	}
	time.Sleep(delay)
}

// ==================== DNS OVER HTTPS ====================

type DoHResolver struct {
	endpoints []string
	cache      *DNSCache
	client     *http.Client
}

type DoHResponse struct {
	Answer []string `json:"Answer"`
}

func NewDoHResolver(ttl time.Duration) *DoHResolver {
	return &DoHResolver{
		endpoints: []string{
			"https://cloudflare-dns.com/dns-query",
			"https://dns.google/resolve",
			"https://dns.quad9.net/dns-query",
		},
		cache: NewDNSCache(ttl),
		client: &http.Client{
			Timeout: 5 * time.Second,
		},
	}
}

func (d *DoHResolver) Resolve(domain string) ([]string, error) {
	// Check cache first
	if ips, err := d.cache.Get(domain); err == nil {
		return ips, nil
	}
	
	// Try DoH endpoints in parallel
	results := make(chan []string, len(d.endpoints))
	errors := make(chan error, len(d.endpoints))
	
	for _, endpoint := range d.endpoints {
		go func(ep string) {
			ips, err := d.queryDoH(ep, domain)
			if err != nil {
				errors <- err
				return
			}
			results <- ips
		}(endpoint)
	}
	
	// Return first successful result
	for i := 0; i < len(d.endpoints); i++ {
		select {
		case ips := <-results:
			d.cache.Set(domain, ips)
			return ips, nil
		case err := <-errors:
			log.Printf("DoH endpoint failed: %v", err)
		case <-time.After(5 * time.Second):
			continue
		}
	}
	
	// Fallback to system DNS
	return net.LookupHost(domain)
}

func (d *DoHResolver) queryDoH(endpoint, domain string) ([]string, error) {
	reqURL := endpoint + "?name=" + domain + "&type=A"
	req, err := http.NewRequest("GET", reqURL, nil)
	if err != nil {
		return nil, err
	}
	
	req.Header.Set("Accept", "application/dns-json")
	
	resp, err := d.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	
	if resp.StatusCode != 200 {
		return nil, fmt.Errorf("DoH returned status %d", resp.StatusCode)
	}
	
	var dohResponse DoHResponse
	if err := json.NewDecoder(resp.Body).Decode(&dohResponse); err != nil {
		return nil, err
	}
	
	return dohResponse.Answer, nil
}

// ==================== DNS CACHE ====================

type DNSCache struct {
	entries map[string]*CacheEntry
	mutex   sync.RWMutex
	ttl     time.Duration
}

type CacheEntry struct {
	IPs      []string
	ExpireAt time.Time
}

func NewDNSCache(ttl time.Duration) *DNSCache {
	return &DNSCache{
		entries: make(map[string]*CacheEntry),
		ttl:     ttl,
	}
}

func (dc *DNSCache) Get(domain string) ([]string, error) {
	dc.mutex.RLock()
	entry, exists := dc.entries[domain]
	dc.mutex.RUnlock()
	
	if exists && time.Now().Before(entry.ExpireAt) {
		return entry.IPs, nil
	}
	
	return nil, fmt.Errorf("cache miss or expired")
}

func (dc *DNSCache) Set(domain string, ips []string) {
	dc.mutex.Lock()
	defer dc.mutex.Unlock()
	
	dc.entries[domain] = &CacheEntry{
		IPs:      ips,
		ExpireAt: time.Now().Add(dc.ttl),
	}
}

// ==================== CONNECTION POOL ====================

type ConnectionPool struct {
	pools   map[string]*HostPool
	mutex   sync.RWMutex
	maxIdle int
	maxAge  time.Duration
}

type HostPool struct {
	idle   []*PooledConn
	active int
	mutex  sync.Mutex
}

type PooledConn struct {
	conn   net.Conn
	usedAt time.Time
	pool   *HostPool
}

// Implement net.Conn interface
func (pc *PooledConn) Read(b []byte) (n int, err error) {
	return pc.conn.Read(b)
}

func (pc *PooledConn) Write(b []byte) (n int, err error) {
	return pc.conn.Write(b)
}

func (pc *PooledConn) Close() error {
	pc.pool.mutex.Lock()
	defer pc.pool.mutex.Unlock()
	
	pc.pool.active--
	
	if len(pc.pool.idle) < 10 {
		pc.usedAt = time.Now()
		pc.pool.idle = append(pc.pool.idle, pc)
		return nil
	}
	
	return pc.conn.Close()
}

func (pc *PooledConn) LocalAddr() net.Addr {
	return pc.conn.LocalAddr()
}

func (pc *PooledConn) RemoteAddr() net.Addr {
	return pc.conn.RemoteAddr()
}

func (pc *PooledConn) SetDeadline(t time.Time) error {
	return pc.conn.SetDeadline(t)
}

func (pc *PooledConn) SetReadDeadline(t time.Time) error {
	return pc.conn.SetReadDeadline(t)
}

func (pc *PooledConn) SetWriteDeadline(t time.Time) error {
	return pc.conn.SetWriteDeadline(t)
}

func NewConnectionPool(maxIdle int, maxAge time.Duration) *ConnectionPool {
	return &ConnectionPool{
		pools:   make(map[string]*HostPool),
		maxIdle: maxIdle,
		maxAge:  maxAge,
	}
}

func (cp *ConnectionPool) Get(target string) (net.Conn, error) {
	cp.mutex.RLock()
	pool, exists := cp.pools[target]
	cp.mutex.RUnlock()
	
	if !exists {
		cp.mutex.Lock()
		pool = &HostPool{}
		cp.pools[target] = pool
		cp.mutex.Unlock()
	}
	
	pool.mutex.Lock()
	defer pool.mutex.Unlock()
	
	if len(pool.idle) > 0 {
		conn := pool.idle[len(pool.idle)-1]
		pool.idle = pool.idle[:len(pool.idle)-1]
		
		if time.Since(conn.usedAt) < cp.maxAge {
			pool.active++
			return conn, nil
		}
		conn.conn.Close()
	}
	
	newConn, err := net.Dial("tcp", target)
	if err != nil {
		return nil, err
	}
	
	pool.active++
	return &PooledConn{
		conn:   newConn,
		usedAt: time.Now(),
		pool:   pool,
	}, nil
}

// ==================== HEALTH CHECKER ====================

type HealthStatus int

const (
	Healthy HealthStatus = iota
	Degraded
	Unhealthy
)

type HealthChecker struct {
	interval time.Duration
	timeout  time.Duration
}

func NewHealthChecker(interval, timeout time.Duration) *HealthChecker {
	return &HealthChecker{
		interval: interval,
		timeout:  timeout,
	}
}

func (hc *HealthChecker) CheckTarget(target string) HealthStatus {
	conn, err := net.DialTimeout("tcp", target, hc.timeout)
	if err != nil {
		return Unhealthy
	}
	conn.Close()
	
	return Healthy
}