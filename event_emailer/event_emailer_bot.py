import asyncio
import logging
from typing import Dict, Any

from pymongo import AsyncMongoClient

from flexus_client_kit import ckit_client
from flexus_client_kit import ckit_cloudtool
from flexus_client_kit import ckit_bot_exec
from flexus_client_kit import ckit_shutdown
from flexus_client_kit import ckit_ask_model
from flexus_client_kit import ckit_mongo

from event_emailer import event_emailer_install
from event_emailer import event_emailer_tools

logger = logging.getLogger("event_emailer")

BOT_NAME = "event_emailer"
BOT_VERSION = "0.2.1"

TOOLS = event_emailer_tools.TOOLS


async def bot_main_loop(fclient: ckit_client.FlexusClient, rcx: ckit_bot_exec.RobotContext) -> None:
    setup = ckit_bot_exec.official_setup_mixing_procedure(
        event_emailer_install.EVENT_EMAILER_SETUP_SCHEMA,
        rcx.persona.persona_setup,
    )

    mongo_conn_str = await ckit_mongo.mongo_fetch_creds(fclient, rcx.persona.persona_id)
    mongo = AsyncMongoClient(mongo_conn_str)
    dbname = rcx.persona.persona_id + "_db"
    mydb = mongo[dbname]
    event_state = mydb["event_state"]

    @rcx.on_updated_message
    async def updated_message_in_db(msg: ckit_ask_model.FThreadMessageOutput):
        pass

    @rcx.on_updated_thread
    async def updated_thread_in_db(th: ckit_ask_model.FThreadOutput):
        pass

    @rcx.on_tool_call(event_emailer_tools.CALENDAR_OPS_TOOL.name)
    async def toolcall_calendar_ops(toolcall: ckit_cloudtool.FCloudtoolCall, model_produced_args: Dict[str, Any]) -> str:
        return await event_emailer_tools.handle_calendar_ops(
            fclient,
            rcx,
            setup,
            toolcall,
            model_produced_args,
        )

    @rcx.on_tool_call(event_emailer_tools.SHEET_OPS_TOOL.name)
    async def toolcall_sheet_ops(toolcall: ckit_cloudtool.FCloudtoolCall, model_produced_args: Dict[str, Any]) -> str:
        return await event_emailer_tools.handle_sheet_ops(
            fclient,
            rcx,
            setup,
            toolcall,
            model_produced_args,
        )

    @rcx.on_tool_call(event_emailer_tools.EMAIL_OPS_TOOL.name)
    async def toolcall_email_ops(toolcall: ckit_cloudtool.FCloudtoolCall, model_produced_args: Dict[str, Any]) -> str:
        return await event_emailer_tools.handle_email_ops(
            fclient,
            rcx,
            setup,
            toolcall,
            model_produced_args,
        )

    @rcx.on_tool_call(event_emailer_tools.STATE_OPS_TOOL.name)
    async def toolcall_state_ops(toolcall: ckit_cloudtool.FCloudtoolCall, model_produced_args: Dict[str, Any]) -> str:
        return await event_emailer_tools.handle_state_ops(
            event_state,
            toolcall,
            model_produced_args,
        )

    try:
        while not ckit_shutdown.shutdown_event.is_set():
            await rcx.unpark_collected_events(sleep_if_no_work=10.0)

    finally:
        logger.info("%s exit", rcx.persona.persona_id)
        mongo.close()


def main():
    scenario_fn = ckit_bot_exec.parse_bot_args()
    fclient = ckit_client.FlexusClient(
        ckit_client.bot_service_name(BOT_NAME, BOT_VERSION),
        endpoint="/v1/jailed-bot",
    )

    asyncio.run(ckit_bot_exec.run_bots_in_this_group(
        fclient,
        marketable_name=BOT_NAME,
        marketable_version_str=BOT_VERSION,
        bot_main_loop=bot_main_loop,
        inprocess_tools=TOOLS,
        scenario_fn=scenario_fn,
        install_func=event_emailer_install.install,
    ))


if __name__ == "__main__":
    main()
