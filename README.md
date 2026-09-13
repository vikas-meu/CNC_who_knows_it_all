# OpenClaw CNC

## AI-Powered Whiteboard Plotter on Arduino UNO Q
![OpenClaw CNC](images/openclaw-cnc.jpg)
OpenClaw CNC is an AI-powered physical whiteboard plotter built around the Arduino UNO Q.

It allows users to control a real CNC plotter using natural-language instructions. Instead of displaying an AI response on a screen, the system physically writes text and draws images on a whiteboard using a marker.

The system combines an Arduino UNO Q, STM32 real-time control, Python, Flask, OpenClaw, Google Gemini, Telegram, and a belt-driven X/Y CNC mechanism.

A simple instruction such as:

"Write HAPPY BIRTHDAY MOM"

can be converted into a physical drawing task and executed directly on the whiteboard.

## Project Overview

OpenClaw CNC is designed as a conversational physical-AI system.

The project separates high-level intelligence from real-time motion control.

The Linux side of the Arduino UNO Q handles:

• Python application
• Flask API
• AI agent integration
• Google Gemini
• Telegram communication
• Web interface
• Task scheduling
• Drawing preparation

The STM32 side handles:

• Real-time stepper control
• X/Y motion
• Servo-controlled pen lift
• Motion-level task control
• Pause and cancellation handling

The Arduino UNO Q Bridge connects these two environments.

## Key Features

### Natural-Language Control

Control the CNC using simple instructions instead of traditional CNC software.

Examples:

"Draw a cat"

"Write HELLO WORLD"

"Draw something for my mom's birthday"

"Clean the board"

### Telegram Control

The CNC can be controlled through Telegram using an OpenClaw-based AI agent.

The agent interprets the user's message and converts it into an appropriate CNC operation.

### AI Task Planning

OpenClaw and Google Gemini provide the high-level reasoning layer.

The AI agent can determine:

• What the user wants
• Which CNC operation is required
• Whether a space estimation is necessary
• Whether text or image drawing should be used
• Which API endpoint should be called

### Text Writing

The CNC can write text directly onto a whiteboard.

The requested text is converted into drawing strokes and executed by the plotter.

### Image Drawing

Images can be processed into drawable paths and executed by the CNC.

Image processing is handled by the Python side of the application.

### Workspace Estimation

The `/estimate` endpoint allows the system to check whether requested content will fit within the configured drawing area.

This allows the AI agent to check the workspace before starting a long physical operation.

### Pause and Resume

Running tasks can be paused without returning the machine to its home position.

When paused:

• Motion stops
• Current position is preserved
• The task remains active

When resumed, the task continues from its next required operation.

### Task Cancellation

A running task can be cancelled through the available control interfaces.

The cancellation sequence is:

Cancel
↓
Stop task
↓
Lift pen
↓
Return to home position
↓
Task finished

### Auto-Homing

After cancellation, the CNC automatically returns to `(0,0)`.

The pen is lifted before the gantry moves to prevent unwanted marks on the whiteboard.

### Live Task Status

The system exposes task status through the API and web interface.

This allows the user to monitor whether the CNC is:

• IDLE
• RUNNING
• PAUSED
• COMPLETED
• CANCELLED
• In an error state

### Self-Cleaning

The CNC includes a cleaning operation that can wipe the whiteboard.

Cleaning is integrated into the task system so that it can also be interrupted.

### Task Scheduling

The system supports scheduled writing operations.

This allows tasks to be queued for a future time, such as automatically writing a message every morning.

### Web Control

A Flask-based web interface provides direct control of the CNC.

The interface can be used for:

• Text writing
• Image drawing
• Board cleaning
• Pause
• Resume
• Cancel
• Task monitoring

## System Architecture

The overall architecture is:

User
↓
Telegram / Web Dashboard
↓
OpenClaw AI Agent
↓
Google Gemini
↓
Flask CNC API
↓
Arduino UNO Q Linux
↓
Arduino UNO Q Bridge
↓
STM32
↓
Stepper Drivers + Servo
↓
X/Y CNC Gantry
↓
Marker
↓
Whiteboard

## Hardware

The current design uses:

• Arduino UNO Q 4GB
• 2 × NEMA 17 stepper motors
• 2 × TMC2209 or A4988 stepper drivers
• 1 × SG90 / MG90S servo
• GT2 timing belts
• 20T GT2 pulleys
• Ø8 mm smooth rods
• LM8UU bearings
• 2020 aluminum extrusion
• 3D-printed marker holder
• 12V 5A power supply
• 5V buck converter
• Wall-mounted whiteboard

## Mechanical System

The plotter uses a belt-driven two-axis CNC mechanism.

The X-axis provides horizontal movement across the whiteboard.

The Y-axis provides vertical movement.

A servo-controlled mechanism acts as the pen lift.

The marker therefore has two primary states:

PEN UP
The marker is lifted while travelling between strokes.

PEN DOWN
The marker contacts the whiteboard while drawing.

## Electronics

The basic power architecture is:

12V PSU
│
├── X Motor Driver → X NEMA 17
│
├── Y Motor Driver → Y NEMA 17
│
└── Buck Converter → 5V
│
├── Arduino UNO Q
└── Servo

The Arduino UNO Q communicates with the stepper drivers and servo through the STM32 control layer.

A common ground should be maintained between the relevant control electronics and power system.

The servo should be powered from an appropriate regulated supply rather than directly from a logic GPIO pin.

## Software Architecture

The project is divided into two main software environments.

### Linux / Python Side

The Linux side provides the high-level application layer.

Responsibilities include:

• Flask REST API
• Task management
• Text generation and processing
• Image processing
• Scheduling
• Web interface
• Communication with the AI agent
• Communication with the STM32 side

### STM32 Side

The STM32 is responsible for real-time machine control.

Responsibilities include:

• Stepper pulse generation
• X-axis control
• Y-axis control
• Servo control
• Motion execution
• Motion-level task state handling

## Project Structure

The repository is organized into the following major components:

CNC_who_knows_it_all/

```
app.yaml

python/
    main.py
    image_to_gcode.py
    requirements.txt
    schedule.json

sketch/
    sketch.ino
    sketch.yaml
```

### python/

Contains the Linux-side CNC application.

`main.py`

Main Flask application and CNC task-management layer.

`image_to_gcode.py`

Handles image-to-drawing-path processing.

`requirements.txt`

Python dependencies required by the application.

`schedule.json`

Stores scheduled task information.

### sketch/

Contains the STM32-side firmware.

`sketch.ino`

Responsible for real-time motion control, stepper movement, servo control, and task-state handling.

`sketch.yaml`

Contains the configuration required for the UNO Q STM32 application.

### app.yaml

Arduino App Lab application configuration.

The current configuration exposes the application on port `5000`.

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/vikas-meu/CNC_who_knows_it_all.git
cd CNC_who_knows_it_all
```

### 2. Arduino UNO Q Setup

Install and configure the Arduino UNO Q using Arduino App Lab.

Connect the UNO Q to your computer and deploy the application.

After the Linux environment is available, connect to the board through SSH.

### 3. Install Required Linux Packages

```bash
sudo apt update
sudo apt upgrade -y

sudo apt install -y git python3 python3-pip python3-venv curl
```

### 4. Install uv

This project can use `uv` as the Python package manager.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Reload the shell environment:

```bash
source ~/.bashrc
```

### 5. Install Python Dependencies

Enter the Python application directory:

```bash
cd python
```

Create the virtual environment:

```bash
uv venv .venv
```

Activate it:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
uv pip install -r requirements.txt
```

### 6. Start the CNC API

Run:

```bash
python main.py
```

The Flask API should become available on:

```text
http://fruity-Q.local:5000
```

The hostname may differ depending on your network configuration.

## Testing the API

Once the Flask application is running, test the task-status endpoint:

```bash
curl http://fruity-Q.local:5000/task/status
```

The API should return the current task state.

## STM32 Firmware

The STM32 firmware is located inside:

```text
sketch/sketch.ino
```

Open the sketch using Arduino IDE with the appropriate Arduino UNO Q STM32 board support installed.

Upload the firmware to the STM32 side of the UNO Q.

## Calibration

Calibration is required before reliable plotting.

The primary values that need to be calibrated include:

• Pen-up servo position
• Pen-down servo position
• X steps per millimeter
• Y steps per millimeter

### Steps-per-Millimeter Calibration

A simple method is to draw a known-size square.

For example:

100 mm × 100 mm

Measure the physical result.

If the actual dimension differs from the expected dimension, adjust the configured steps-per-millimeter values.

Repeat until the measured dimension matches the requested dimension.

## AI Agent Integration

OpenClaw provides the agent layer that connects natural-language commands to the CNC API.

The agent can be configured to understand the available CNC operations and their purpose.

The AI agent should understand operations such as:

`/estimate`

`/write_text`

`/draw_image`

`/clean`

`/task/status`

`/task/pause`

`/task/resume`

`/task/cancel`

## Telegram Integration

Create a Telegram bot using BotFather.

Obtain the bot token and provide it to the application or OpenClaw environment.

Example environment variable:

```bash
export TELEGRAM_BOT_TOKEN="YOUR_TOKEN"
```

Never commit your Telegram token to the repository.

## Gemini Integration

The AI reasoning layer can use Google Gemini.

Configure your Gemini API key as an environment variable:

```bash
export GEMINI_API_KEY="YOUR_API_KEY"
```

Never commit API keys to the repository.

## Example Workflow

A typical command looks like this:

User:

"Write HELLO WORLD"

↓

Telegram

↓

OpenClaw

↓

Gemini understands the request

↓

CNC API

↓

Space estimation

↓

Task creation

↓

Background worker

↓

Arduino UNO Q Bridge

↓

STM32

↓

Stepper motors

↓

Pen movement

↓

HELLO WORLD appears on the whiteboard

## Task Management

Long-running CNC operations should not block the main API process.

Instead, the operation is handled as a background task.

This allows the system to continue receiving commands while the machine is working.

This architecture is essential for supporting:

• Pause
• Resume
• Cancel
• Live status
• Task scheduling

## Safety Model

The project implements safety at the task and motion layers rather than relying only on the user interface.

During motion execution, task state can be checked before movement operations.

Conceptually:

```python
if task.cancelled:
    raise TaskCancelled()

if task.paused:
    task.pause_event.wait()
```

Cancellation then triggers the safe shutdown sequence:

```text
Cancel
↓
Stop current task
↓
Lift pen
↓
Return to (0,0)
```

## Graceful Degradation

Some functionality depends on optional Python packages, particularly image-processing functionality.

The application is designed so that optional dependencies do not necessarily prevent the core API from starting.

This allows features such as text writing, task management, cleaning, and scheduling to remain available even if image-processing functionality needs to be repaired or reinstalled.

## API Overview

The project exposes a Flask-based API.

Important endpoints include:

`/write_text`

Create a text-writing task.

`/draw_image`

Create an image-drawing task.

`/estimate`

Estimate the size and workspace requirements of a drawing.

`/clean`

Start the board-cleaning operation.

`/task/status`

Return the current task state.

`/task/pause`

Pause the active task.

`/task/resume`

Resume the paused task.

`/task/cancel`

Cancel the active task and initiate the safe return-to-home process.

## Example Text Request

A basic text request can be made using:

```bash
curl -X POST http://fruity-Q.local:5000/write_text \
     -H "Content-Type: application/json" \
     -d '{"text":"HELLO","x":50,"y":50,"size":20}'
```

## Troubleshooting

### CNC does not move

Check:

• STM32 firmware is uploaded
• Stepper drivers are powered
• Motors are correctly connected
• STEP/DIR wiring is correct
• Common ground is connected
• Motor-driver current is configured correctly

### Motor moves in the wrong direction

Swap the appropriate motor coil polarity or invert the direction configuration in the firmware.

### Drawing dimensions are incorrect

Recalibrate:

• X steps/mm
• Y steps/mm

Use a measured test square to determine the required correction.

### Pen does not lift correctly

Adjust the servo pen-up and pen-down positions.

Make sure the mechanical linkage does not bind.

### Image drawing dependencies fail to install

Check the Python package configuration and the available ARM64 wheels.

Image processing is optional, so the core CNC functionality can still be used while the image-processing dependency is repaired.

## Current Capabilities

The current project provides:

• AI-assisted CNC control
• Natural-language commands
• Telegram control
• Web control
• Text plotting
• Image drawing
• Workspace estimation
• Task scheduling
• Live task status
• Pause
• Resume
• Cancellation
• Automatic return-to-home
• Whiteboard cleaning
• Arduino UNO Q + STM32 architecture

## Future Development

Possible future improvements include:

### Closed-Loop Vision

Add a CSI camera for visual verification of the drawing.

Potential capabilities:

• Detect whether the marker produced the expected line
• Verify completed drawings
• Detect drawing errors
• Perform visual corrections

### Voice Control

Add speech-to-text so the user can give spoken instructions.

```text
Voice
↓
Speech-to-Text
↓
OpenClaw
↓
CNC API
↓
Physical Drawing
```

### Multi-Color Marker System

Add an automatic marker carousel so the robot can select different marker colors.

### Public Drawing Interface

Allow authenticated users to send drawings to the physical whiteboard remotely.

### Expanded Physical AI

The architecture can potentially be adapted to other physical systems such as:

• Pick-and-place robots
• Engraving systems
• Dispensing machines
• Educational robots
• Laboratory automation
• Other AI-controlled CNC systems

## Why This Project?

Traditional CNC machines generally require specialized software, predefined toolpaths, and technical knowledge.

OpenClaw CNC explores a different interaction model.

Instead of:

User → CAD/CAM → G-code → CNC

the goal is:

User → Natural Language → AI Agent → CNC → Physical Result

This makes the machine accessible through a conversational interface while retaining the deterministic control required by a physical motion system.

## Project Philosophy

The goal of OpenClaw CNC is not simply to add AI to a CNC machine.

The goal is to explore how AI agents can safely interact with physical machines.

A useful physical AI system should be able to:

Understand a task.

Plan an action.

Execute the action.

Report its state.

Respond to the user.

Pause when requested.

Resume correctly.

Cancel safely.

Return to a known physical state.

## Demo

Project demonstration:

https://youtu.be/c1oOR3uuYOA

## Repository

GitHub:

https://github.com/vikas-meu/CNC_who_knows_it_all

## Technologies

Arduino UNO Q

STM32

Python

Flask

OpenClaw

Google Gemini

Telegram

OpenCV

NEMA 17 Stepper Motors

TMC2209 Stepper Drivers

## Author

Built by Vikas Singh Thakur.

The project is developed as an exploration of robotics, AI agents, CNC automation, and physical AI.

## License

Add the license that you want to use for this project before publishing the repository.

If you intend this project to be open source, consider adding a `LICENSE` file to the repository and specifying the license here.

## Contributing

Contributions, improvements, bug reports, and ideas are welcome.

If you build an extension of OpenClaw CNC or adapt the architecture for another physical AI application, consider opening an issue or pull request.

## Acknowledgements

Built using:

Arduino UNO Q
Arduino App Lab
OpenClaw
Google Gemini
Python
Flask
Telegram

OpenClaw CNC is an experiment in making physical machines more conversational, accessible, and responsive.
