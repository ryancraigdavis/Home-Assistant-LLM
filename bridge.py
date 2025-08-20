#!/usr/bin/env python3
"""
Voice Assistant Bridge Script
Connects Rhasspy → LLM → Home Assistant
"""

import json
import logging
import time
import os
import requests
import paho.mqtt.client as mqtt
from typing import Dict, List, Any
from pathlib import Path


# Configuration
class Config:
    # MQTT Settings
    MQTT_HOST = "localhost"
    MQTT_PORT = 1883

    # LLM Settings (Update with your LLM server details)
    LLM_HOST = os.getenv("LLM_HOST")
    LLM_PORT = 11434  # Ollama default port
    LLM_MODEL = os.getenv("LLM_MODEL", "llama3.1:8b")  # Default to llama3.1 if not set

    # Home Assistant Settings (Update with your HA details)
    HA_HOST = os.getenv("HA_HOST")
    HA_PORT = 8123
    HA_TOKEN = os.getenv("HA_TOKEN")

    # MQTT Topics
    TOPIC_ASR = "hermes/asr/textCaptured"
    TOPIC_TTS = "hermes/tts/say"
    TOPIC_HOTWORD = "hermes/hotword/detected"


class VoiceAssistantBridge:
    def __init__(self):
        self.setup_logging()
        self.load_entities()
        self.setup_mqtt()

    def setup_logging(self):
        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
        )
        self.logger = logging.getLogger(__name__)
        
    def load_entities(self):
        """Load discovered entities from JSON file"""
        entities_file = Path("ha_entities.json")
        
        if entities_file.exists():
            try:
                with open(entities_file, 'r') as f:
                    self.entities = json.load(f)
                self.logger.info(f"Loaded {sum(len(v) for v in self.entities.values())} entities")
            except Exception as e:
                self.logger.error(f"Error loading entities: {e}")
                self.entities = self.get_default_entities()
        else:
            self.logger.warning("No ha_entities.json found, using defaults")
            self.entities = self.get_default_entities()
            
    def get_default_entities(self):
        """Fallback entity structure if JSON not found"""
        return {
            'lights': [],
            'switches': [],
            'climate': [],
            'fans': [],
            'automations': [],
            'scripts': [],
            'media_players': [],
            'covers': [],
            'sensors': [],
            'other': []
        }
        
    def generate_entity_list(self):
        """Generate entity list for system prompt"""
        entity_lines = []
        
        for light in self.entities.get('lights', []):
            entity_lines.append(f"- {light['entity_id']} ({light['friendly_name']})")
            
        for switch in self.entities.get('switches', []):
            entity_lines.append(f"- {switch['entity_id']} ({switch['friendly_name']})")
            
        for climate in self.entities.get('climate', []):
            entity_lines.append(f"- {climate['entity_id']} ({climate['friendly_name']})")
            
        for fan in self.entities.get('fans', []):
            entity_lines.append(f"- {fan['entity_id']} ({fan['friendly_name']})")
            
        for automation in self.entities.get('automations', []):
            entity_lines.append(f"- {automation['entity_id']} ({automation['friendly_name']})")
            
        for script in self.entities.get('scripts', []):
            entity_lines.append(f"- {script['entity_id']} ({script['friendly_name']})")
            
        return "\n".join(entity_lines)

    def setup_mqtt(self):
        """Setup MQTT client and callbacks"""
        self.mqtt_client = mqtt.Client()
        self.mqtt_client.on_connect = self.on_mqtt_connect
        self.mqtt_client.on_message = self.on_mqtt_message

        try:
            self.mqtt_client.connect(Config.MQTT_HOST, Config.MQTT_PORT, 60)
            self.logger.info(
                f"Connected to MQTT broker at {Config.MQTT_HOST}:{Config.MQTT_PORT}"
            )
        except Exception as e:
            self.logger.error(f"Failed to connect to MQTT: {e}")

    def on_mqtt_connect(self, client, userdata, flags, rc):
        """Called when MQTT connects"""
        if rc == 0:
            self.logger.info("MQTT connected successfully")
            # Subscribe to voice recognition
            client.subscribe(Config.TOPIC_ASR)
            client.subscribe(Config.TOPIC_HOTWORD)
            self.logger.info(f"Subscribed to {Config.TOPIC_ASR}")
        else:
            self.logger.error(f"MQTT connection failed with code {rc}")

    def on_mqtt_message(self, client, userdata, message):
        """Called when MQTT message received"""
        try:
            topic = message.topic
            payload = json.loads(message.payload.decode())

            self.logger.info(f"Received MQTT message on {topic}: {payload}")

            if topic == Config.TOPIC_ASR:
                self.handle_voice_input(payload)
            elif topic == Config.TOPIC_HOTWORD:
                self.handle_hotword(payload)

        except Exception as e:
            self.logger.error(f"Error processing MQTT message: {e}")

    def handle_hotword(self, payload):
        """Handle wake word detection"""
        wake_word = payload.get("modelId", "unknown")
        self.logger.info(f"Wake word detected: {wake_word}")

    def handle_voice_input(self, payload):
        """Handle voice transcription from Rhasspy"""
        user_text = payload.get("text", "")
        session_id = payload.get("sessionId", "default")

        self.logger.info(f"Processing voice input: '{user_text}'")

        if not user_text or user_text == "[unk]":
            response = "I didn't catch that. Could you please repeat?"
            self.send_tts_response(response, session_id)
            return

        # Send to LLM for processing
        try:
            llm_response = self.query_llm(user_text)
            self.process_llm_response(llm_response, session_id)
        except Exception as e:
            self.logger.error(f"Error processing with LLM: {e}")
            error_response = "Sorry, I'm having trouble processing that request."
            self.send_tts_response(error_response, session_id)

    def query_llm(self, user_text: str) -> Dict[str, Any]:
        """Send text to LLM and get response"""

        # Generate dynamic system prompt with discovered entities
        entity_list = self.generate_entity_list()
        
        system_prompt = f"""You are a helpful home assistant AI. You can control smart home devices and have natural conversations.

Available Home Assistant functions:
- light_control(entity_id, action, brightness=None): Control lights (action: turn_on, turn_off, toggle)
- switch_control(entity_id, action): Control switches (action: turn_on, turn_off, toggle)  
- climate_control(entity_id, temperature=None, mode=None): Control climate
- automation_control(entity_id, action): Control automations (action: trigger, turn_on, turn_off, toggle)
- script_control(entity_id, action): Control scripts (action: run, turn_on, turn_off, toggle)
- create_reminder(text, time): Create reminders

When controlling devices, respond with both conversation AND function calls in JSON format:
{{
  "speech": "Your spoken response",
  "functions": [
    {{"name": "light_control", "parameters": {{"entity_id": "light.living_room", "action": "turn_on", "brightness": 80}}}}
  ]
}}

For regular conversation, just respond normally without functions.

Current available entities:
{entity_list}

Examples:
User: "Turn on the living room lights"
Response: {{"speech": "Turning on the living room lights", "functions": [{{"name": "light_control", "parameters": {{"entity_id": "light.living_room", "action": "turn_on"}}}}]}}

User: "Run the morning routine"
Response: {{"speech": "Starting your morning routine", "functions": [{{"name": "automation_control", "parameters": {{"entity_id": "automation.morning_routine", "action": "trigger"}}}}]}}

User: "How's it going?"
Response: "I'm doing well! How can I help you today?"
"""

        url = f"http://{Config.LLM_HOST}:{Config.LLM_PORT}/api/generate"

        payload = {
            "model": Config.LLM_MODEL,
            "prompt": f"System: {system_prompt}\n\nUser: {user_text}\n\nAssistant:",
            "stream": False,
            "options": {"temperature": 0.1, "top_p": 0.9},
        }

        self.logger.info(f"Sending to LLM: {user_text}")

        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()

        result = response.json()
        llm_text = result.get("response", "").strip()

        self.logger.info(f"LLM response: {llm_text}")
        return {"response": llm_text}

    def process_llm_response(self, llm_response: Dict[str, Any], session_id: str):
        """Process LLM response and execute any home assistant commands"""

        response_text = llm_response.get("response", "")

        # Try to parse as JSON for function calls
        try:
            if response_text.startswith("{") and response_text.endswith("}"):
                parsed = json.loads(response_text)
                speech_response = parsed.get("speech", response_text)
                functions = parsed.get("functions", [])

                # Execute function calls
                for func in functions:
                    self.execute_ha_function(func)

                # Send speech response
                self.send_tts_response(speech_response, session_id)
            else:
                # Regular conversation response
                self.send_tts_response(response_text, session_id)

        except json.JSONDecodeError:
            # Not JSON, treat as regular text
            self.send_tts_response(response_text, session_id)

    def execute_ha_function(self, function_call: Dict[str, Any]):
        """Execute Home Assistant function calls"""

        func_name = function_call.get("name")
        params = function_call.get("parameters", {})

        self.logger.info(f"Executing HA function: {func_name} with params: {params}")

        try:
            if func_name == "light_control":
                self.control_light(params)
            elif func_name == "switch_control":
                self.control_switch(params)
            elif func_name == "climate_control":
                self.control_climate(params)
            elif func_name == "create_reminder":
                self.create_reminder(params)
            elif func_name == "automation_control":
                self.control_automation(params)
            elif func_name == "script_control":
                self.control_script(params)
            else:
                self.logger.warning(f"Unknown function: {func_name}")

        except Exception as e:
            self.logger.error(f"Error executing HA function {func_name}: {e}")

    def control_light(self, params: Dict[str, Any]):
        """Control Home Assistant lights"""
        entity_id = params.get("entity_id")
        action = params.get("action")
        brightness = params.get("brightness")

        if action == "turn_on":
            service_data = {"entity_id": entity_id}
            if brightness is not None:
                service_data["brightness"] = int(
                    brightness * 255 / 100
                )  # Convert to 0-255
            self.call_ha_service("light", "turn_on", service_data)

        elif action == "turn_off":
            self.call_ha_service("light", "turn_off", {"entity_id": entity_id})

        elif action == "toggle":
            self.call_ha_service("light", "toggle", {"entity_id": entity_id})

    def control_switch(self, params: Dict[str, Any]):
        """Control Home Assistant switches"""
        entity_id = params.get("entity_id")
        action = params.get("action")

        if action in ["turn_on", "turn_off", "toggle"]:
            self.call_ha_service("switch", action, {"entity_id": entity_id})

    def control_climate(self, params: Dict[str, Any]):
        """Control Home Assistant climate"""
        entity_id = params.get("entity_id")
        temperature = params.get("temperature")
        mode = params.get("mode")

        service_data = {"entity_id": entity_id}
        if temperature:
            service_data["temperature"] = temperature
        if mode:
            service_data["hvac_mode"] = mode

        self.call_ha_service("climate", "set_temperature", service_data)

    def create_reminder(self, params: Dict[str, Any]):
        """Create reminder in Home Assistant"""
        text = params.get("text")
        time_str = params.get("time")

        # This would integrate with HA calendar or notification system
        self.logger.info(f"Creating reminder: {text} at {time_str}")
        # Implementation depends on your HA setup
        
    def control_automation(self, params: Dict[str, Any]):
        """Control Home Assistant automations"""
        entity_id = params.get("entity_id")
        action = params.get("action", "trigger")
        
        if action == "trigger":
            self.call_ha_service("automation", "trigger", {"entity_id": entity_id})
        elif action == "turn_on":
            self.call_ha_service("automation", "turn_on", {"entity_id": entity_id})
        elif action == "turn_off":
            self.call_ha_service("automation", "turn_off", {"entity_id": entity_id})
        elif action == "toggle":
            self.call_ha_service("automation", "toggle", {"entity_id": entity_id})
            
    def control_script(self, params: Dict[str, Any]):
        """Control Home Assistant scripts"""
        entity_id = params.get("entity_id")
        action = params.get("action", "run")
        
        if action in ["run", "turn_on"]:
            self.call_ha_service("script", "turn_on", {"entity_id": entity_id})
        elif action == "turn_off":
            self.call_ha_service("script", "turn_off", {"entity_id": entity_id})
        elif action == "toggle":
            self.call_ha_service("script", "toggle", {"entity_id": entity_id})

    def call_ha_service(self, domain: str, service: str, service_data: Dict[str, Any]):
        """Call Home Assistant service via API"""

        url = (
            f"http://{Config.HA_HOST}:{Config.HA_PORT}/api/services/{domain}/{service}"
        )

        headers = {
            "Authorization": f"Bearer {Config.HA_TOKEN}",
            "Content-Type": "application/json",
        }

        self.logger.info(
            f"Calling HA service: {domain}.{service} with data: {service_data}"
        )

        response = requests.post(url, headers=headers, json=service_data, timeout=10)
        response.raise_for_status()

        self.logger.info(f"HA service call successful: {response.status_code}")

    def send_tts_response(self, text: str, session_id: str = "default"):
        """Send text-to-speech response back to Rhasspy"""

        tts_payload = {"text": text, "siteId": "default", "sessionId": session_id}

        self.logger.info(f"Sending TTS response: {text}")

        self.mqtt_client.publish(Config.TOPIC_TTS, json.dumps(tts_payload))

    def run(self):
        """Start the bridge service"""
        self.logger.info("Starting Voice Assistant Bridge...")

        try:
            self.mqtt_client.loop_forever()
        except KeyboardInterrupt:
            self.logger.info("Shutting down...")
            self.mqtt_client.disconnect()


if __name__ == "__main__":
    # Create and run the bridge
    bridge = VoiceAssistantBridge()
    bridge.run()
