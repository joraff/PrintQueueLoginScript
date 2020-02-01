#!/usr/bin/env bash

# Ensure the log file exists
touch "/Library/Logs/OAL Queue Manager.log"

# Its OK for non-admin users to read this file
chmod 755 "/Library/Logs/OAL Queue Manager.log"
