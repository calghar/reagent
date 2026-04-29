package version

// Version is overridden at link time via -ldflags "-X .../version.Version=...".
var Version = "0.0.0-dev"
