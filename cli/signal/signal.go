// Package signal provides graceful shutdown handling for CLI commands
package signal

import (
	"context"
	"os"
	"os/signal"
	"sync"
	"syscall"
)

var (
	// ctx is the global context that gets cancelled on interrupt
	ctx    context.Context
	cancel context.CancelFunc
	once   sync.Once

	// interrupted indicates if an interrupt was received
	interrupted bool
	mu          sync.RWMutex
)

// Setup initializes signal handling. Call this once at the start of the program.
func Setup() context.Context {
	once.Do(func() {
		ctx, cancel = context.WithCancel(context.Background())

		sigChan := make(chan os.Signal, 1)
		signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)

		go func() {
			<-sigChan
			mu.Lock()
			interrupted = true
			mu.Unlock()
			cancel()
		}()
	})
	return ctx
}

// Context returns the global context that cancels on interrupt
func Context() context.Context {
	if ctx == nil {
		return Setup()
	}
	return ctx
}

// IsInterrupted returns true if an interrupt signal was received
func IsInterrupted() bool {
	mu.RLock()
	defer mu.RUnlock()
	return interrupted
}

// CheckInterrupt returns an error if interrupted, nil otherwise
func CheckInterrupt() error {
	if IsInterrupted() {
		return ErrInterrupted
	}
	return nil
}

// ErrInterrupted is returned when the operation was cancelled by user interrupt
var ErrInterrupted = &InterruptError{}

// InterruptError represents a user interrupt
type InterruptError struct{}

func (e *InterruptError) Error() string {
	return "operation cancelled"
}

// IsInterruptError checks if an error is an interrupt error
func IsInterruptError(err error) bool {
	_, ok := err.(*InterruptError)
	return ok
}

