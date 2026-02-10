# Demo: Progress Indicators for Long Operations

This document provides demo steps for showcasing the progress indicators feature in SciDK.

## Feature Overview

**What it does**: Provides real-time visual feedback during long-running operations (scans, commits, reconciliations) including:
- Progress bars with percentage completion
- Real-time status updates (e.g., "Processing file 50/200...")
- Estimated time remaining
- Cancel button to abort operations
- Responsive UI that doesn't block during operations

## Prerequisites

1. SciDK application running (default: http://localhost:5000)
2. A directory with multiple files for scanning (20+ files recommended for visible progress)

## Demo Steps

### 1. Demonstrate Background Scan with Progress Tracking

**Goal**: Show progress bar, status updates, and ETA during a scan operation.

**Steps**:
1. Navigate to the Files page (`/datasets`)
2. In the "Provider Browser" section:
   - Select "Filesystem" as the provider
   - Select or enter a directory path with 20+ files
   - Click "🔍 Scan This Folder"
3. Observe the "Scans Summary" section below:
   - **Progress bar appears** showing completion percentage
   - **Status message updates** in real-time (e.g., "Processing 50/200 files... (25/s)")
   - **ETA displays** time remaining (e.g., "~2m remaining")
   - Progress bar color: blue (running) → green (completed)

**Expected Output**:
```
scan running — /path/to/data — 50/200 (25%) — Processing 50/200 files... (25/s) — ~1m remaining [Cancel]
[Progress bar: ████████░░░░░░░░ 25%]
```

### 2. Demonstrate Real-Time Status Updates

**Goal**: Show different status messages as the scan progresses.

**Steps**:
1. Start a scan on a large directory (100+ files)
2. Watch the status message change through different phases:
   - "Initializing scan..."
   - "Counting files..."
   - "Processing 500 files..."
   - "Processing 150/500 files... (50/s)"

**What to highlight**:
- Status messages provide context about what's happening
- Messages update automatically without page refresh
- Processing rate (files/second) is calculated and displayed

### 3. Demonstrate Commit Progress

**Goal**: Show progress tracking for Neo4j commit operations.

**Steps**:
1. Complete a scan first (or use an existing scan)
2. In the "Scans Summary" section, find your scan
3. Click "Commit to Graph" button
4. Observe progress updates:
   - "Preparing commit..."
   - "Committing to in-memory graph..."
   - "Building commit rows..."
   - "Built commit rows: 200 files, 50 folders"
   - "Writing to Neo4j..."

**Expected Output**:
```
commit running — /path/to/data — 200/201 (99%) — Writing to Neo4j...
[Progress bar: ███████████████░ 99%]
```

### 4. Demonstrate Cancel Functionality

**Goal**: Show that long-running operations can be canceled.

**Steps**:
1. Start a scan on a large directory (500+ files)
2. While the scan is running, locate the "Cancel" button next to the task
3. Click "Cancel"
4. Observe:
   - Task status changes to "canceled"
   - Progress bar stops updating
   - Operation terminates gracefully

**What to highlight**:
- Cancel button only appears for running tasks
- Canceled tasks are marked clearly
- System remains stable after cancellation

### 5. Demonstrate UI Responsiveness

**Goal**: Show that the UI remains interactive during long operations.

**Steps**:
1. Start a long-running scan (100+ files)
2. While scan is in progress, try these interactions:
   - Click the "Refresh" button → Works immediately
   - Browse to a different folder → Navigation works
   - Click through tabs → UI remains responsive
   - Start another scan (up to 2 concurrent tasks) → Works

**What to highlight**:
- Page doesn't freeze or become unresponsive
- Background tasks run independently
- User can continue working while operations complete

### 6. Demonstrate Multiple Concurrent Tasks

**Goal**: Show that multiple operations can run simultaneously with individual progress tracking.

**Steps**:
1. Start a scan on directory A
2. Immediately start a scan on directory B
3. Observe:
   - Both scans show independent progress bars
   - Each has its own status message and ETA
   - Both complete successfully

**System Limits**:
- Default: Maximum 2 concurrent background tasks
- Configurable via `SCIDK_MAX_BG_TASKS` environment variable

### 7. Demonstrate Progress History

**Goal**: Show completed tasks remain visible for reference.

**Steps**:
1. Complete several scan/commit operations
2. Observe the "Scans Summary" section:
   - Completed tasks show "completed" status
   - Progress bars are green
   - All metadata preserved (file count, duration, path)
   - Click scan ID or path to view details

## Key Features Demonstrated

✅ **Progress bars** - Visual indication of completion percentage
✅ **Real-time status updates** - "Processing file 50/200..."
✅ **Estimated time remaining** - "~2m remaining"
✅ **UI remains responsive** - No blocking during operations
✅ **Cancel button** - Ability to abort long operations
✅ **Processing rate** - Shows files/second throughput
✅ **Multiple concurrent tasks** - Up to 2 operations simultaneously
✅ **Graceful completion** - Green progress bar when done

## Technical Details

### Architecture
- **Backend**: Python threading for background tasks in `/api/tasks` endpoint
- **Frontend**: JavaScript polling (1-second interval) to fetch task status
- **Progress Calculation**: `processed / total` for percentage, rate-based ETA

### API Endpoints
- `POST /api/tasks` - Create background task (scan or commit)
- `GET /api/tasks` - List all tasks with progress
- `GET /api/tasks/<id>` - Get specific task details
- `POST /api/tasks/<id>/cancel` - Cancel running task

### Progress Fields
```json
{
  "id": "task_id_here",
  "type": "scan",
  "status": "running",
  "progress": 0.5,
  "processed": 100,
  "total": 200,
  "eta_seconds": 120,
  "status_message": "Processing 100/200 files... (50/s)",
  "started": 1234567890.0,
  "ended": null
}
```

## Troubleshooting

**Progress not updating**:
- Check browser console for errors
- Verify polling is active (1-second interval)
- Check backend logs for task worker errors

**ETA not shown**:
- ETA calculated after processing >10 files
- Very fast operations may complete before ETA displays
- This is normal behavior

**Tasks stuck at "running"**:
- Check backend process isn't hung
- Verify file permissions for scan directory
- Check system resources (CPU, memory)

## Future Enhancements (Not in This Release)

- Server-Sent Events (SSE) for more efficient real-time updates
- WebSocket support for instant progress streaming
- Estimated time remaining for commit operations
- Detailed operation logs accessible from UI
- Resume capability for canceled operations
- Priority queue for task scheduling
