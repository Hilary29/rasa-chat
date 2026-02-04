# This files contains your custom actions which can be used to run
# custom Python code.
#
# See this guide on how to implement these action:
# https://rasa.com/docs/rasa/custom-actions

from typing import Any, Text, Dict, List

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, Restarted, AllSlotsReset


class ActionClearTransactionSlots(Action):
    """Réinitialise uniquement les slots de transaction après confirmation/annulation."""

    def name(self) -> Text:
        return "action_clear_transaction_slots"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:

        # Réinitialise les slots de transaction
        return [
            SlotSet("amount", None),
            SlotSet("phone_number", None),
            SlotSet("neero_id", None),
            SlotSet("currency", None),
        ]


class ActionRestart(Action):
    """Réinitialise complètement la conversation (tous les slots + historique)."""

    def name(self) -> Text:
        return "action_restart"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:

        dispatcher.utter_message(text="Conversation réinitialisée. Comment puis-je vous aider ?")
        return [Restarted()]
