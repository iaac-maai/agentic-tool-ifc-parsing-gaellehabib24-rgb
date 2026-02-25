#!/usr/bin/env python3
"""
IFC Parser tool example for use with Google Gemini API.
This demonstrates how to use the IFC parser tool with Gemini function calling.
"""

import google.generativeai as genai
import os
from dotenv import load_dotenv

from ifc_parse import parse_ifc_file, ifc_parse_tool


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

    # Create the model with the IFC parser tool
    model = genai.GenerativeModel(
        model_name='gemini-2.5-flash',
        tools=[ifc_parse_tool]
    )

    # Start a chat session
    chat = model.start_chat()

    # Example prompt that should trigger the IFC parser tool
    prompt = "Parse the IFC file at 'sample.ifc' and tell me how many walls, doors, and windows are in the building."
    print(f"User: {prompt}\n")

    response = chat.send_message(prompt)

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

        print(f"Tool called: {function_call.name}")
        
        # Handle args safely (may be None)
        args = dict(function_call.args) if function_call.args else {}
        print(f"Arguments: {args}\n")

        # Execute the function
        if function_call.name == "parse_ifc":
            result = parse_ifc_file(
                file_path=args.get('file_path', '')
            )
        else:
            result = {"error": "Unknown function"}

        print(f"Tool result: {result}\n")

        # Send the result back to Gemini
        response = chat.send_message(
            genai.protos.Content(
                parts=[genai.protos.Part(
                    function_response=genai.protos.FunctionResponse(
                        name=function_call.name,
                        response=result
                    )
                )]
            )
        )

    # Print the final response
    if response.candidates[0].content.parts:
        print(f"Assistant: {response.text}")
    else:
        print("No response generated.")


if __name__ == "__main__":
    main()
