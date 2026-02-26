#!/usr/bin/env python3
"""
IFC Parser tool example for use with Google Gemini API.
This demonstrates how to use the IFC parser tool with Gemini function calling.
"""

import google.generativeai as genai
import os
from dotenv import load_dotenv

from ifc_parse import parse_ifc_file, ifc_parse_tool
import ifcopenshell
from tools.checker_building_code import (
    check_space_compliance,
    analyze_window_compliance,
    analyze_evacuation_routes,
)


def main():
    """Main function to demonstrate the IFC parser tool usage with Gemini."""

    # Load environment variables from .env file
    load_dotenv()

    # Configure the API key
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        print(
            "Error: GEMINI_API_KEY environment variable not set.\n"
            "You must supply a valid key to authenticate with Gemini.\n"
            "Create a `.env` file (you can copy `.env.example`) or set the variable in your shell:\n"
            "  PowerShell: $env:GEMINI_API_KEY='your_key'\n"
            "  bash/zsh: export GEMINI_API_KEY='your_key'\n"
        )
        return

    genai.configure(api_key=api_key)

    # Define Gemini tools for the parser and compliance checkers
    checker_space_tool = genai.protos.Tool(
        function_declarations=[
            genai.protos.FunctionDeclaration(
                name="check_space_compliance",
                description="Run space compliance checks on an IFC file",
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={
                        "file_path": genai.protos.Schema(
                            type=genai.protos.Type.STRING,
                            description="Path to the IFC file to check"
                        )
                    },
                    required=["file_path"]
                )
            )
        ]
    )

    checker_window_tool = genai.protos.Tool(
        function_declarations=[
            genai.protos.FunctionDeclaration(
                name="analyze_window_compliance",
                description="Analyze window compliance for an IFC file",
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={
                        "file_path": genai.protos.Schema(
                            type=genai.protos.Type.STRING,
                            description="Path to the IFC file to check"
                        )
                    },
                    required=["file_path"]
                )
            )
        ]
    )

    checker_evac_tool = genai.protos.Tool(
        function_declarations=[
            genai.protos.FunctionDeclaration(
                name="analyze_evacuation_routes",
                description="Analyze evacuation routes for an IFC file",
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={
                        "file_path": genai.protos.Schema(
                            type=genai.protos.Type.STRING,
                            description="Path to the IFC file to check"
                        )
                    },
                    required=["file_path"]
                )
            )
        ]
    )

    # Create the model with all registered tools
    model = genai.GenerativeModel(
        model_name='gemini-2.5-flash',
        tools=[t for t in (ifc_parse_tool, checker_space_tool, checker_window_tool, checker_evac_tool) if t]
    )

    print("\n🏗️  IFC Parser Agent Ready!")
    print("Examples: 'Parse sample.ifc', 'What spaces are there?', 'Check building code compliance'")
    print("Type 'exit' to quit.\n")

    # Interactive chat loop
    while True:
        try:
            user_prompt = input("You: ").strip()
        except EOFError:
            print("Goodbye!")
            break

        if user_prompt.lower() == 'exit':
            print("Goodbye!")
            break

        if not user_prompt:
            continue

        # Start a new chat session for each conversation
        chat = model.start_chat()

        # Send user message
        response = chat.send_message(user_prompt)

        # Handle function calls
        max_iterations = 10
        iteration = 0
        
        while iteration < max_iterations and response.candidates[0].content.parts:
            iteration += 1
            
            # Check if there's a function call
            if not hasattr(response.candidates[0].content.parts[0], 'function_call'):
                break
                
            function_call = response.candidates[0].content.parts[0].function_call
            
            # Check if function_call is None or has no name
            if function_call is None or not function_call.name:
                break

            print(f"[Tool called: {function_call.name}]")
            
            # Handle args safely (may be None)
            args = dict(function_call.args) if function_call.args else {}

            # Execute the function
            if function_call.name == "parse_ifc":
                result = parse_ifc_file(
                    file_path=args.get('file_path', 'sample.ifc')
                )
            elif function_call.name == "check_space_compliance":
                fp = args.get('file_path', 'sample.ifc')
                try:
                    m = ifcopenshell.open(fp)
                    result = check_space_compliance(m)
                except Exception as e:
                    result = {"error": f"Failed to run space compliance: {e}"}
            elif function_call.name == "analyze_window_compliance":
                fp = args.get('file_path', 'sample.ifc')
                try:
                    m = ifcopenshell.open(fp)
                    result = analyze_window_compliance(m)
                except Exception as e:
                    result = {"error": f"Failed to run window compliance: {e}"}
            elif function_call.name == "analyze_evacuation_routes":
                fp = args.get('file_path', 'sample.ifc')
                try:
                    m = ifcopenshell.open(fp)
                    result = analyze_evacuation_routes(m)
                except Exception as e:
                    result = {"error": f"Failed to run evacuation analysis: {e}"}
            else:
                result = {"error": "Unknown function"}

            # Prepare payload: Gemini's proto marshal expects a mapping
            if isinstance(result, dict):
                response_payload = result
            else:
                # wrap lists or other values in a mapping so proto can marshal
                response_payload = {"results": result}

            # Send the result back to Gemini
            response = chat.send_message(
                genai.protos.Content(
                    parts=[genai.protos.Part(
                        function_response=genai.protos.FunctionResponse(
                            name=function_call.name,
                            response=response_payload
                        )
                    )]
                )
            )

        # Print the assistant response
        if response.candidates[0].content.parts:
            print(f"Assistant: {response.text}\n")
        else:
            print("No response generated.\n")


if __name__ == "__main__":
    main()
