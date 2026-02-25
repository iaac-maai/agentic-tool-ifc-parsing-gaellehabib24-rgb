#!/usr/bin/env python3
"""
Simple tool example for use with Google Gemini API.
This demonstrates how to define and use function calling with Gemini.
"""

import google.generativeai as genai
import os
from dotenv import load_dotenv

from calculator_tool import calculate, calculate_tool


def main():
    """Main function to demonstrate the tool usage with Gemini."""

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

    # Create the model with the tool
    model = genai.GenerativeModel(
        model_name='gemini-2.5-flash',
        tools=[calculate_tool]
    )

    # Start a chat session
    chat = model.start_chat()

    # Example prompt that should trigger the tool
    prompt = "What is 25 multiplied by 4, and then add 10 to that result?"
    print(f"User: {prompt}\n")

    response = chat.send_message(prompt)

    # Handle function calls
    while response.candidates[0].content.parts[0].function_call:
        function_call = response.candidates[0].content.parts[0].function_call

        print(f"Tool called: {function_call.name}")
        print(f"Arguments: {dict(function_call.args)}\n")

        # Execute the function
        if function_call.name == "calculate":
            result = calculate(
                operation=function_call.args['operation'],
                a=function_call.args['a'],
                b=function_call.args['b']
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
    print(f"Assistant: {response.text}")


if __name__ == "__main__":
    main()
