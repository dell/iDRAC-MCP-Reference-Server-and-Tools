# Reference iDRAC MCP Server and Tools

- [Reference iDRAC MCP Server and Tools](#reference-idrac-mcp-server-and-tools)
  - [Navigation](#navigation)
  - [So, what is the point of this repo?](#so-what-is-the-point-of-this-repo)
  - [What is MCP?](#what-is-mcp)
  - [What do I do with Reference iDRAC MCP Server?](#what-do-i-do-with-reference-idrac-mcp-server)
  - [Architecture Details](#architecture-details)
  - [Getting Started](#getting-started)
    - [Project Structure](#project-structure)
    - [Quick Start](#quick-start)
    - [Available Tools](#available-tools)
    - [Hardware and System Requirements](#hardware-and-system-requirements)
    - [External Dependency for Large Language Models](#external-dependency-for-large-language-models)
    - [iDRAC License Requirements](#idrac-license-requirements)
  - [What to do next?/Installation](#what-to-do-nextinstallation)
  - [Post Installation](#post-installation)
  - [Debugging](#debugging)
  - [Default Ports Used by the Framework](#default-ports-used-by-the-framework)
  - [FAQ](#faq)
    - [How should I deploy MCP server in my environment?](#how-should-i-deploy-mcp-server-in-my-environment)
    - [How is authentication addressed in this implementation?](#how-is-authentication-addressed-in-this-implementation)
    - [Do I need to worry about MCP tool calls overwhelming the iDRAC link?](#do-i-need-to-worry-about-mcp-tool-calls-overwhelming-the-idrac-link)
    - [Is MCP reference solution vendor neutral?](#is-mcp-reference-solution-vendor-neutral)
  - [LICENSE](#license)
  - [Contributing](#contributing)
  - [Disclaimer](#disclaimer)
  - [Support](#support)

## Navigation

- [Main README](README.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Debugging](docs/DEBUGGING.md)
- [Install](docs/DEPLOY.md)

## So, what is the point of this repo?

This project delivers a reference implementation of an iDRAC MCP server, allowing AI agents or LLMs to natively interface with Dell PowerEdge servers via iDRAC Redfish APIs.

iDRAC MCP server shall ideally run in a containerized environment. This server shall not run on iDRAC itself and will not consume any iDRAC resources.

We tried hard to write these instructions such that things would be easy to follow. If you have feedback, especially 
if something was confusing, feel free to open an [issue](https://github.com/dell/Reference-iDRAC-MCP-Server-and-Tools/issues)

## What is MCP?

MCP (Model Context Protocol) is an open-source standard for connecting AI applications to external systems.
Using MCP, AI applications like Claude or ChatGPT can connect to data sources (e.g. local files, databases), tools (e.g. search engines, calculators) and workflows (e.g. specialized prompts)—enabling them to access key information and perform tasks across live or offline external datasources. In the context of agentic workflows, monitorning and configuration interface of PowerEdge iDRACs can be utilized by the MCP server to expose AI native tool call interfaces to AI applications. 

Think of MCP like a USB-C port for AI applications. Just as USB-C provides a standardized way to connect electronic devices, MCP provides a standardized way to connect AI applications to external systems.

MCP is a vendor-neutral standardized to discover and invoke MCP tool calls. For more to get started on MCP, See [developer resources](https://modelcontextprotocol.io/docs/getting-started/intro) 

You can also read the latest specification at [developer resources](https://modelcontextprotocol.io/specification/2025-06-18). 

## What do I do with Reference iDRAC MCP Server?

The most common question that follows is: “What can I actually do with it?”
This reference server provides native integration with agentic workflows through the Model Context Protocol (MCP), an open standard designed for AI tool discovery and invocation.

AI applications natively discover and invoke calls on the tools supported by MCP servers. The MCP reference server provdied in this repository communicates with PowerEdge servers using DMTF Redfish APIs, a standardized interface for out-of-band server management. This integration enables AI agents (by leveraging MCP server tools) to perform tasks such as monitoring, configuration, and lifecycle operations across modern server racks, as well as implement automated monitoring and failure resolution workflows.

You can read further about the reference iDRAC MCP Server design philosophy at [Design Philosophy](docs/DESIGN_PHILOSOPHY.md)


## Architecture Details

A high level reference deployment of iDRAC MPC Server will look as depicted in the picture below.

![High level Deployment Overview](docs/deployment_overview.png)

For deep dive architecture details of reference iDRAC MPC Server, See [ARCHITECTURE.md](docs/ARCHITECTURE.md)

The deployment view of agentic integration test suite which is provided with in the repo can be depicted in the picture below.
![Integration Test Deployment View](docs/agentic_integration_tests_overview.png)

For deep dive architecture details of agentic integration test suite, See [ARCHITECTURE_AGENTIC_INTEGRATION_TEST.md](docs/ARCHITECTURE_AGENTIC_INTEGRATION_TEST.md)

## Getting Started
The MCP reference server communicates with PowerEdge servers using DMTF Redfish APIs, which provide a standardized interface for server management. Redfish-based manageability is available by default with the base tier of iDRAC licensing, ensuring essential management capabilities without requiring additional upgrades on the target.

### Project Structure
```
mcp_server/
├── mcp_idrac_server/              # MCP Server
|── integration_tests_agentic/     # Integration Test Suite with agentic interactions (LLM/natural language based chat interactions).
└── docs/                          # Documentation which includes architeture and user guides.
├── mcp_client_examples/           # Simple Client Examples
└── integration_tests/             # Simple Integration Test Suite for CI/CD integration purposes.
```

### Quick Start
Show docker deployment

### Available Tools
Tool call support is the cornerstone of this solution’s usability. In this reference implementation, we have adopted an approach where tools are user-configurable. The implementation exposes a variety of tool calls, allowing users to select and define which tools their instance of the iDRAC MCP server will provide by configuring the mcp_idrac_server/config/tools.yaml file.

The Redfish methods supported by iDRAC are defined in the OpenAPI.yaml, which is publicly available as specified by the DMTF Redfish standard. This reference implementation includes a script that converts the Redfish OpenAPI definition into MCP tool calls, enabling seamless integration. The resulting reference tool definitions are provided in mcp_idrac_server/config/tools_reference.yaml.

We encourage users to review this reference YAML and choose the tool calls that best fit their use cases.

Users can pick and choose the tools and add it in to tools.yaml. The default setting includes tools like:
- **System Management:** get_system_info, list_systems, get_service_root
- **Power Control:** reset_system, reset_manager
- **BIOS Configuration:** get_bios_settings, get_bios_pending_settings, get_bios_registry
- **Hardware Inventory:** get_memory_info, get_storage_info, get_ethernet_interfaces, get_processors
- **User Management:** list_user_accounts, get_user_account, create_user_account, update_user_account, delete_user_account

Workflows combine multiple tools into sequential operations that include data flow, conditional execution, and error handling. The underlying API calls are abstracted within these workflow tool calls, allowing them to be executed as a single request to the MCP server (and thus to LLMs) thus enabling token efficiency.

You can read further about the reference iDRAC MCP Server design philosophy for tool execution support at [Design Philosophy](docs/DESIGN_PHILOSOPHY.md)


### Hardware and System Requirements

Whatever server on which you decide to run this reference MCP server and tools will have to run the following applications:

- A few lightweight Python programs
- Docker containers

The amount of resources you will need strongly depends on the number of servers from which you will need to tie in together in to this solutions. We 
are still in the initial phases of testing but here are some stats from a 5-minute capture of a live R760 during the integration test execution:

| Total Packets               | 276               |
|-----------------------------|-------------------|
| Average PPS                 | 2                 |
| Average Packet Size (Bytes) | 720               |
| Total Bytes sent/recv       | 69122 (~0.06MB)   |
| Average bytes/s             | 230               |

As you can see from the above, the data load is very light. You could easily manage thousands of servers or server racks with 
one MCP server installation depending on its resources. As we perform more load testing we will push results here.

#### External Dependency for Large Language Models
The reference agents which is part of the integration suite shall require access to an external LLM configured through yaml definition. The solution was tested with GPT-OSS 120B model as a reference. 

GPT-OSS 120B is an open-weight language model developed by OpenAI, featuring 117 billion parameters and utilizing a Mixture-of-Experts architecture. It is designed for advanced reasoning capabilities and can run efficiently on a single 80GB GPU. The model is released under the Apache 2.0 license, allowing organizations to deploy, download, and own it.

The test infrastructure shall work with the variety of models as configured through yaml definition.

#### iDRAC License Requirements
The MCP reference server communicates with PowerEdge servers using DMTF Redfish APIs, which provide a standardized interface for server management. Redfish-based manageability is available by default with the base tier of iDRAC licensing, ensuring essential management capabilities without requiring additional upgrades.

## What to do next?/Installation

After you have gone through getting started. You can head over to our [installation instructions](docs/DEPLOY.md).

**NOTE:** You will need access to the internet for the initial build of the pipeline but can move it offline after 
it is built.

## Post Installation

After you have your setup running you will likely want to start customizing it to your liking. This is meant to be a 
reference architecture but it is unlikely it will do exactly what you want. You will likely want to add your own tool calls.

## Debugging

If you need to debug things, we have included a few tips and tricks we learned along the way in 
[DEBUGGING.md](docs/DEBUGGING.md).

## Default Ports Used by the Framework

- 8000 - idrac-mcp-server default port
- 8001 - Agentic orchestrator defualt port (component of agentic integration test suite)
- 8501 - Streamlit based web interface (component of agentic integration test suite)

## FAQ
### How should I deploy MCP server in my environment?
The deployment of the MCP server should be tailored to your specific use case. This reference implementation is intended as a guideline only and does not address individual customer deployment scenarios. It is the responsibility of the consumer to customize and adapt this implementation to meet their unique requirements.

### How is authentication addressed in this implementation?
The MCP protocol specification keeps the authentication workflow optional and flexible, allowing it to adapt to different deployment scenarios. In many cases, the MCP server resides within the trusted domain of the agent, and the agent or any other applications in that trust domain abstracts the authentication process.

This reference implementation does not include authentication workflows in its initial version.

The integration test suite provides a method to discover and onboard PowerEdge iDRACs into the agentic trust domain. For more details, refer to the architectural description.

### Do I need to worry about MCP tool calls overwhelming the iDRAC link?
There is no risk that even with significant workflow definitions with tool calls can overwhelm iDRAC's 1Gb/s link. Each tool calls shall only take few KB/s. This can be considered comparable to the regular system management workflow traffic.

### Is MCP reference solution vendor neutral?
Yes. MCP server is implemented based on the industry standard MCP protocol and will use DMTFs Redfish interface to communicate with server endpoints. While there are parts of the Redfish standard which are left to vendor implementation Dell's Redfish implementation is compliant with the specification.

## LICENSE
This project is licensed under Apache 2.0 License. See the [LICENSE](LICENSE.md) for more information.

## Contributing
We welcome your contributions to this reference toolset. See [Contributing Guidelines](CONTRIBUTING.md) for 
more details. Please reference our [Code of Conduct](CODE_OF_CONDUCT.md).

## Disclaimer
The software applications included in this package are  considered "BETA". They are intended for testing use in 
non-production  environments only. 

No support is implied or offered. Dell Corporation assumes no  responsibility for results or performance of "BETA" 
files.  Dell does NOT warrant that the Software will meet your requirements, or that operation of the Software will 
be uninterrupted or error free. The Software is provided to you "AS IS" without warranty of any kind. DELL DISCLAIMS 
ALL WARRANTIES, EXPRESS OR IMPLIED, INCLUDING, WITHOUT LIMITATION, THE IMPLIED WARRANTIES OF MERCHANTABILITY, FITNESS 
FOR A PARTICULAR PURPOSE, TITLE AND NON-INFRINGEMENT. The entire risk as to the results and performance of the Software
is assumed by you. No technical support provided with this Software. 

IN NO EVENT SHALL DELL OR ITS SUPPLIERS BE LIABLE FOR ANY DIRECT OR INDIRECT DAMAGES WHATSOEVER (INCLUDING, WITHOUT 
LIMITATION, DAMAGES FOR LOSS OF BUSINESS PROFITS, BUSINESS INTERRUPTION, LOSS OF BUSINESS INFORMATION, OR OTHER 
PECUNIARY LOSS) ARISING OUT OF USE OR INABILITY TO USE THE SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH 
DAMAGES. Some jurisdictions do not allow an exclusion or limitation of liability for consequential or incidental 
damages, so the above limitation may not apply to you.

## Support
- To report an issue open one [here](https://github.com/dell/Reference-iDRAC-MCP-Server-and-Tools/issues).
- If any requirements have not been addressed, then create an issue [here](https://github.com/dell/Reference-iDRAC-MCP-Server-and-Tools/issues).
- To provide feedback to the development team, email **idracMCPServerTeam@dell.com**.


