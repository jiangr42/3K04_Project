# ADC to Management System Communication Protocol
This document defines the messages exchanged between the ADC controller and the external management system. It is the reference for both `external_communication_driver.py` and the management system side.

## 1. Overview

- **Initiator:** the management system always initiates. The controller never sends a message unless it is answering a request.
- **Device ID:** each controller has a unique, settable `device_id`. Every request names the device it is for, and every response names the device that sent it. See section 3.1.
- **One request, one response:** every request addressed to a device receives exactly one response from that device. The management system must wait for the response, or a timeout, before sending the next request to the same device. That is how a response is matched to its request.
- **Request types:** `get` reads a value from the controller. `set` changes a value on the controller.

## 2. Framing

- Each message is a single JSON object, UTF-8 encoded, on a single line, terminated by `\n`.
- Messages must not contain literal newlines. JSON escapes newlines inside strings as `\n`, so this happens automatically with `json.dumps`.
- Each device has its own serial line to the management system, so only one controller ever sees a given message.
- Timestamps are Unix time in seconds (float).
- Field names are `snake_case`.

## 3. Message format

### Request (management system → controller)

```json
{
  "device_id": "ADC-01",
  "type": "get",
  "target": "inventory",
  "params": { "cabinet": "1" }
}
```

| Field    | Type    | Required | Description |
|----------|---------|----------|-------------|
| `device_id` | string | yes   | The device the request is for. `"*"` means "whichever device is on this line", but is only allowed for `get controller_state`. |
| `type`   | string  | yes      | `"get"` or `"set"`. |
| `target` | string  | yes      | What to read or change. See sections 5 and 6. |
| `params` | object  | no       | Target-specific parameters. Omit, or send `{}`, if there are none. |

### Response (controller → management system)

```json
{
  "device_id": "000",
  "type": "response",
  "target": "inventory",
  "status": 0,
  "status_name": "SUCCESS",
  "data": { ... }
}
```

| Field         | Type    | Present          | Description |
|---------------|---------|------------------|-------------|
| `device_id`   | string  | always           | The responding device's own ID. |
| `type`        | string  | always           | Always `"response"`. |
| `target`      | string  | always           | Copied from the request. `null` if the request could not be parsed. |
| `status`      | integer | always           | Result code. See section 4. |
| `status_name` | string  | always           | Readable name of `status`. |
| `data`        | object  | `get` success    | The requested values. |
| `field`       | string or list | `set` only | The field or fields the request changed, or attempted to change. |

### 3.1 Device addressing

- A controller handles a request only if the request's `device_id` equals its own ID. If the ID does not match, the controller does not act on the request and responds with `8 WRONG_DEVICE`. Because the response carries the controller's real ID, the management system can tell which device is actually on that line.
- `"*"` is only valid with `get controller_state`. It lets the management system find the ID of a device it does not know yet, for example a newly connected one. Any other request sent to `"*"` gets `8 WRONG_DEVICE`.
- The response's `device_id` is always the responding device's own ID, including in error responses.
- Device IDs must be unique across all devices connected to the management system. The controller cannot check this, so the management system is responsible for not assigning the same ID twice.

## 4. Status codes

These codes are defined in `src/modules/status_codes.py`, and the controller modules return the same codes, so a module's result is sent to the management system as is. Codes 9 and up in that file are only used inside the controller (log in and state changes) and are never sent.

| Code | Name             | Meaning |
|------|------------------|---------|
| 0    | `SUCCESS`        | Request completed. |
| 1    | `ERROR`          | Internal or system error on the controller, for example a file could not be read or written. |
| 2    | `NOT_FOUND`      | The referenced item does not exist, for example an unknown username. |
| 3    | `ALREADY_EXISTS` | The item being added already exists. |
| 4    | `INVALID_REQUEST`| The message is malformed: invalid JSON, not a JSON object, a missing required field or param, or an unknown `type`. |
| 5    | `UNKNOWN_TARGET` | `target` is not recognised for this `type`. |
| 6    | `INVALID_VALUE`  | A parameter is present but its value is not allowed: wrong type (for example `8` where a bool is expected) or out of range (for example an unknown state name). |
| 7    | `REJECTED`       | The request is valid but not allowed in the current state, for example changing the state to `Maintenance` while a user is logged in. |
| 8    | `WRONG_DEVICE`   | The request's `device_id` does not match this controller's ID. Nothing was changed. |

## 5. GET requests

### 5.1 `controller_state`

No params. This is the only request that may be sent to `"*"`. so a device's ID can be discovered. the example below demonstrates that

Controller request:

```json
{ "device_id": "*", "type": "get", "target": "controller_state" }
```
ADC response: 

### 5.2 `auth_details`

Returns user records.

| Param      | Type   | Required | Description |
|------------|--------|----------|-------------|
| `username` | string | no       | Return only this user. Omit to return all users. |

Management system request: 
```json
{ "device_id": "000", "type": "get", "target": "auth_details", "params": { "username": "bob" } }
```

ADC response: 
```json
{
  "device_id": "000", "type": "response", "target": "auth_details",
  "status": 0, "status_name": "SUCCESS",
  "data": {
    "users": [
      {
        "username": "bob",
        "level": "Nurse",
        "last_login_attempt": "1761955100.2",
        "consecutive_failed_attempts": "0",
        "allowed_medication": ["advil", "tylenol"]
      }
    ]
  }
}
```

`last_login_attempt` and `consecutive_failed_attempts` are sent as strings, exactly as stored in the controller's user file. `last_login_attempt` is a Unix timestamp, `"0"` if the user has never attempted to log in.

If `username` is given and does not exist, the response has status `2 NOT_FOUND`.

### 5.3 `inventory`

| Param      | Type   | Required | Description |
|------------|--------|----------|-------------|
| `cabinet`  | string | no       | Return only this cabinet. |
| `medicine` | string | no       | Return only this medicine. |

Management system request:
```json
{ "device_id": "ADC-01", "type": "get", "target": "inventory", "params": { "cabinet": "1" } }
```

ADC response:

### 5.4 `event_logs`

Returns log entries at or above a severity level.

| Param         | Type    | Required | Description |
|---------------|---------|----------|-------------|
| `min_level`   | string  | yes      | `"DEBUG"`, `"INFO"`, `"WARNING"` or `"ERROR"`. |
| `since`       | float   | no       | Only return entries after this timestamp. UNIX Time|
| `max_entries` | integer | no       | Return at most this many entries, newest first. Default 100. |

Management system request:
```json
{ "device_id": "000", "type": "get", "target": "event_logs", "params": { "min_level": "WARNING", "max_entries": 2 } }
```

ADC response:
```json
{
  "device_id": "000", "type": "response", "target": "event_logs",
  "status": 0, "status_name": "SUCCESS",
  "data": {
    "entries": [
      { "timestamp": 1761955180.4, "level": "WARNING", "message": "user bob attempted log in, locked out for 42 more seconds" },
      { "timestamp": 1761955120.9, "level": "WARNING", "message": "user bob attempted log in, password incorrect, failed attempts: 3" }
    ]
  }
}
```

An unknown `min_level` returns status `6 INVALID_VALUE`.

## 6. SET requests

Every `set` response includes `field`, the field or fields the request changed. On failure, `field` still names the field or fields the request attempted to change, so the management system can tell which change failed. `set` responses carry no `data`.

### 6.1 `device_id`

| Param   | Type   | Required | Description |
|---------|--------|----------|-------------|
| `value` | string | yes      | New device ID. Must be non-empty. |

Management system request:
```json
{ "device_id": "000", "type": "set", "target": "device_id", "params": { "value": "001" } }
```
ADC response:
```json
{
  "device_id": "ADC-02", "type": "response", "target": "device_id",
  "status": 0, "status_name": "SUCCESS",
  "field": "device_id"
}
```

The request is addressed to the device's old ID. The response, and every message after it, uses the new ID. If the new ID is the same as the old one, the response is still `SUCCESS`.

### 6.2 `auth_details`

Adds, edits or deletes a user. The `action` param selects which.

| Param                | Type            | Used by              | Description |
|----------------------|-----------------|----------------------|-------------|
| `action`             | string          | all                  | `"add"`, `"edit"` or `"delete"`. |
| `username`           | string          | all                  | The user to act on. |
| `password`           | string          | add (required), edit | |
| `level`              | string          | add (required), edit | |
| `allowed_medication` | tuple of strings| add, edit            | |

On `edit`, include only the fields being changed. `username` cannot be changed. Sending `consecutive_failed_attempts: 0` on edit clears a lockout.

**Add**
Management system request:
```json
{ "device_id": "000", "type": "set", "target": "auth_details",
  "params": { "action": "add", "username": "amy", "password": "pw123", "level": "Admin", "allowed_medication": ["morphine"] } }
```

```json
{ "device_id": "ADC-01", "type": "response", "target": "auth_details",
  "status": 0, "status_name": "SUCCESS", "field": "amy" }
```

**Edit**
Management system request:
```json
{ "device_id": "ADC-01", "type": "set", "target": "auth_details",
  "params": { "action": "edit", "username": "amy", "level": "Nurse", "allowed_medication": ["advil"] } }
```

```json
{ "device_id": "ADC-01", "type": "response", "target": "auth_details",
  "status": 0, "status_name": "SUCCESS", "field": ["amy.level", "amy.allowed_medication"] }
```

**Delete**
Management system request:
```json
{ "device_id": "ADC-01", "type": "set", "target": "auth_details", "params": { "action": "delete", "username": "amy" } }
```

```json
{ "device_id": "ADC-01", "type": "response", "target": "auth_details",
  "status": 2, "status_name": "NOT_FOUND", "field": "amy" }
```

Possible statuses for each action:

| Action | Statuses |
|--------|----------|
| add    | `SUCCESS`, `ERROR`, `ALREADY_EXISTS` |
| edit   | `SUCCESS`, `ERROR`, `NOT_FOUND`, `INVALID_VALUE` (unknown field) |
| delete | `SUCCESS`, `ERROR`, `NOT_FOUND` |

A missing `action` or a missing required param returns `4 INVALID_REQUEST`. An unknown `action`, or a param with a value that is not allowed, returns `6 INVALID_VALUE`.

### 6.3 `state`

Sets the cabinet's state. State names are the same as in `cabinet_controller.py`. `get controller_state` reports the current state in its `state` field.

| Param   | Type   | Required | Description |
|---------|--------|----------|-------------|
| `value` | string | yes      | One of the states the management system may set, listed below. |

| State               | Settable here | Behaviour |
|---------------------|---------------|-----------|
| `Standby`           | yes           | Normal idle state. Nurses and admins can log in. |
| `Maintenance`       | yes           | Only maintenance staff and admins can log in. No dispensing or restocking. |
| `Locked`            | yes           | Only admins can log in. |
| `EmergencyShutdown` | yes           | Only maintenance staff and admins can log in. |
| `Dispensing`        | no            | Entered when a nurse or admin logs in to dispense. |
| `Restocking`        | no            | Entered when a nurse or admin logs in to restock. |
| `Fault`             | no            | Entered by the controller when it detects a fault. Only maintenance staff and admins can log in. The management system clears it by setting another state, for example `Standby`. |

Management system request:
```json
{ "device_id": "000", "type": "set", "target": "state", "params": { "value": "Locked" } }
```

```json
{ "device_id": "ADC-01", "type": "response", "target": "state",
  "status": 0, "status_name": "SUCCESS", "field": "state" }
```

- `Locked` and `EmergencyShutdown` always take effect. If a user is logged in, they are logged out.
- `Standby` and `Maintenance` return `7 REJECTED` while a user is logged in, so a user is not interrupted mid-task.
- `Dispensing`, `Restocking`, `Fault` or an unknown name returns `6 INVALID_VALUE`.

## 7. Error examples

**Unparseable message.** `target` is `null` because the request could not be read.

```json
{ "device_id": "ADC-01", "type": "response", "target": null,
  "status": 4, "status_name": "INVALID_REQUEST" }
```

**Unknown target**

```json
{ "device_id": "ADC-01", "type": "response", "target": "temperature",
  "status": 5, "status_name": "UNKNOWN_TARGET" }
```

**Wrong device.** The request was for `ADC-07`, but the controller on this line is `ADC-01`.

```json
{ "device_id": "ADC-07", "type": "get", "target": "inventory" }
```

```json
{ "device_id": "ADC-01", "type": "response", "target": "inventory",
  "status": 8, "status_name": "WRONG_DEVICE" }
```

## 8. Timing

- The controller handles requests in the order they arrive.
- The management system should treat a request as failed if no response arrives within **2 seconds**. It may then resend the request.
- `get` requests are always safe to resend. A resent `set` may be applied twice, so check the result with a `get` before resending a `set`.
