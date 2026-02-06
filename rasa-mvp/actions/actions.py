# This files contains your custom actions which can be used to run
# custom Python code.
#
# See this guide on how to implement these action:
# https://rasa.com/docs/rasa/custom-actions

from typing import Any, Text, Dict, List, Optional
import csv
import json
import os
import re

from rasa_sdk import Action, Tracker, FormValidationAction
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, UserUtteranceReverted, Restarted
from rasa_sdk.types import DomainDict

from actions.api.user import ActionGetUserInfo  # noqa: F401

INTENT_DESCRIPTION_MAPPING_PATH = os.path.join(
    os.path.dirname(__file__), "intent_description_mapping.csv"
)

class ValidateTransferForm(FormValidationAction):

    def name(self) -> Text:
        return "validate_transfer_form"

    async def required_slots(
        self,
        domain_slots: List[Text],
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> List[Text]:

        transfer_type = tracker.get_slot("transfer_type")

        if not transfer_type:
            return ["transfer_type"]

        if not tracker.get_slot("amount"):
            return ["transfer_type", "amount"]

        if transfer_type == "neero":
            return ["transfer_type", "amount", "neero_id"]
        elif transfer_type == "mobile_money":
            return ["transfer_type", "amount", "phone_number"]

        # Fallback
        return ["transfer_type", "amount"]

    # Intents qui ne sont pas lies au remplissage du formulaire
    NON_FORM_INTENTS = {
        "chitchat", "explain", "out_of_scope", "deny", "cancel_transfer",
        "contact_support", "greet", "goodbye", "thank", "bot_challenge",
        "cant_help", "ask_help", "nlu_fallback", "ask_help_card",
        "why_neero", "feedback", "restart",
    }

    def _is_non_form_intent(self, tracker: Tracker) -> bool:
        intent = tracker.latest_message.get("intent", {}).get("name", "")
        return intent in self.NON_FORM_INTENTS

    async def extract_transfer_type(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:

        # Ne pas extraire si l'intent n'est pas lie au formulaire
        if self._is_non_form_intent(tracker):
            return {}

        # Verifier si deja defini
        current_transfer_type = tracker.get_slot("transfer_type")
        if current_transfer_type:
            return {"transfer_type": current_transfer_type}

        # Essayer d'extraire depuis les entites
        entities = tracker.latest_message.get("entities", [])

        transfer_type_entity = next(
            (e["value"] for e in entities if e["entity"] == "transfer_type"),
            None
        )

        if transfer_type_entity:
            normalized = self._normalize_transfer_type(transfer_type_entity)
            if normalized:
                return {"transfer_type": normalized}

        # Inferer depuis neero_id
        neero_id = tracker.get_slot("neero_id")
        neero_id_entity = next(
            (e["value"] for e in entities if e["entity"] == "neero_id"),
            None
        )
        if neero_id or neero_id_entity:
            return {"transfer_type": "neero"}

        # Inferer depuis phone_number
        phone_number = tracker.get_slot("phone_number")
        phone_entity = next(
            (e["value"] for e in entities if e["entity"] == "phone_number"),
            None
        )
        if phone_number or phone_entity:
            return {"transfer_type": "mobile_money"}

        # Verifier le texte pour des mots-cles
        text = tracker.latest_message.get("text", "").lower()
        if any(kw in text for kw in ["neero", "wallet"]):
            return {"transfer_type": "neero"}
        if any(kw in text for kw in ["mobile", "momo", "orange", "mtn"]):
            return {"transfer_type": "mobile_money"}

        return {"transfer_type": None}

    def _normalize_transfer_type(self, value: str) -> Optional[str]:
        # transforme les valeurs de transfer_type vers 'neero' ou 'mobile_money'
        if not value:
            return None

        value_lower = value.lower().strip()

        neero_keywords = ["neero", "wallet", "wallet neero"]
        mobile_keywords = ["mobile money", "mobile", "momo", "orange money",
                          "mtn momo", "mtn", "orange", "om"]

        if any(kw in value_lower for kw in neero_keywords):
            return "neero"
        if any(kw in value_lower for kw in mobile_keywords):
            return "mobile_money"

        return None

    def validate_transfer_type(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:

        if slot_value in ["neero", "mobile_money"]:
            return {"transfer_type": slot_value}

        if slot_value:
            normalized = self._normalize_transfer_type(slot_value)
            if normalized:
                return {"transfer_type": normalized}

        return {"transfer_type": None}

    def validate_amount(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:

        if not slot_value:
            return {"amount": None}

        try:
            # Gerer les montants en string
            amount_str = str(slot_value).replace(" ", "").replace(",", "")
            amount = int(amount_str)

            if amount <= 0:
                dispatcher.utter_message(
                    text="Le montant doit etre superieur a 0."
                )
                return {"amount": None}

            if amount > 1000000:  # Limite 1 millions
                dispatcher.utter_message(
                    text="Le montant maximum autorise est de 1 000 000 FCFA."
                )
                return {"amount": None}

            return {"amount": str(amount)}

        except ValueError:
            dispatcher.utter_message(
                text="Veuillez entrer un montant valide en chiffres."
            )
            return {"amount": None}

    def validate_neero_id(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:

        if not slot_value:
            return {"neero_id": None}

        # S'assurer qu'il commence par @
        if not slot_value.startswith("@"):
            slot_value = f"@{slot_value}"

        # Validation: @ suivi de 3-20 caracteres alphanumeriques/underscore
        if re.match(r"^@[a-zA-Z0-9_]{3,20}$", slot_value):
            return {"neero_id": slot_value}

        dispatcher.utter_message(
            text="ID Neero invalide. Le format doit etre @username (3-20 caracteres)."
        )
        return {"neero_id": None}

    def validate_phone_number(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:

        if not slot_value:
            return {"phone_number": None}

        # Retirer espaces et tirets
        phone = str(slot_value).replace(" ", "").replace("-", "")

        # Pattern Cameroun: optionnel +237, puis 6 suivi de 8 chiffres
        pattern = r"^(\+?237)?6[0-9]{8}$"

        if re.match(pattern, phone):
            # Normaliser a 9 chiffres (sans code pays)
            if phone.startswith("+237"):
                phone = phone[4:]
            elif phone.startswith("237"):
                phone = phone[3:]
            return {"phone_number": phone}

        dispatcher.utter_message(
            text="Numero de telephone invalide. Format attendu: 6XXXXXXXX"
        )
        return {"phone_number": None}


class ActionSubmitTransfer(Action):

    def name(self) -> Text:
        return "action_submit_transfer"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:

        transfer_type = tracker.get_slot("transfer_type")
        amount = tracker.get_slot("amount")

        if transfer_type == "neero":
            neero_id = tracker.get_slot("neero_id")
            dispatcher.utter_message(
                text=f"Vous souhaitez faire un transfert Neero de {amount} FCFA a l'utilisateur {neero_id}. Confirmez-vous ?",
                buttons=[
                    {"title": "Confirmer", "payload": "/confirm_transfer"},
                    {"title": "Annuler", "payload": "/cancel_transfer"}
                ]
            )
        else:
            phone_number = tracker.get_slot("phone_number")
            dispatcher.utter_message(
                text=f"Vous souhaitez effectuer un transfert mobile money de {amount} FCFA au numero {phone_number}. Confirmez-vous ?",
                buttons=[
                    {"title": "Confirmer", "payload": "/confirm_transfer"},
                    {"title": "Annuler", "payload": "/cancel_transfer"}
                ]
            )

        return []


class ActionClearTransactionSlots(Action):

    def name(self) -> Text:
        return "action_clear_transaction_slots"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:

        return [
            SlotSet("amount", None),
            SlotSet("phone_number", None),
            SlotSet("neero_id", None),
            SlotSet("currency", None),
            SlotSet("transfer_type", None),
        ]


class ActionRestart(Action):
    """Reinitialise completement la conversation (tous les slots + historique)."""

    def name(self) -> Text:
        return "action_restart"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:

        dispatcher.utter_message(text="Conversation reinitialisee. Comment puis-je vous aider ?")
        return [Restarted()]


class ActionAskAffirmation(Action):
    """Disambiguation : propose les top intents sous forme de boutons quand le NLU n'est pas sur."""

    def name(self) -> Text:
        return "action_ask_affirmation"

    def __init__(self) -> None:
        self.intent_mappings = {}
        try:
            with open(INTENT_DESCRIPTION_MAPPING_PATH, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self.intent_mappings[row["intent"].strip()] = row["button"].strip()
        except FileNotFoundError:
            pass

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:

        intent_ranking = tracker.latest_message.get("intent_ranking", [])

        if len(intent_ranking) > 1:
            diff = intent_ranking[0].get("confidence", 0) - intent_ranking[1].get("confidence", 0)
            if diff < 0.2:
                intent_ranking = intent_ranking[:3]
            else:
                intent_ranking = intent_ranking[:1]

        # Filtrer les intents inutiles pour la disambiguation
        exclude = {"nlu_fallback", "out_of_scope"}
        first_intent_names = [
            i.get("name", "") for i in intent_ranking
            if i.get("name", "") not in exclude
        ]

        if first_intent_names:
            entities = tracker.latest_message.get("entities", [])
            entities_dict = {e["entity"]: e["value"] for e in entities}
            entities_json = json.dumps(entities_dict) if entities_dict else ""

            buttons = []
            for intent in first_intent_names:
                button_title = self.intent_mappings.get(intent, intent)
                payload = f"/{intent}{entities_json}" if entities_json else f"/{intent}"
                buttons.append({"title": button_title, "payload": payload})

            buttons.append({"title": "Autre chose", "payload": "/out_of_scope"})

            dispatcher.utter_message(
                text="Je ne suis pas sur d'avoir compris. Vouliez-vous dire :",
                buttons=buttons
            )
        else:
            dispatcher.utter_message(
                text="Je n'ai pas compris votre demande. Pouvez-vous reformuler ?"
            )

        return []


class ActionDefaultFallback(Action):
    """Fallback final : propose de reformuler ou de recommencer."""

    def name(self) -> Text:
        return "action_default_fallback"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:

        dispatcher.utter_message(
            text="Je n'ai pas reussi a comprendre votre demande. Vous pouvez reformuler ou recommencer.",
            buttons=[
                {"title": "Recommencer", "payload": "/restart"},
                {"title": "Contacter le support", "payload": "/contact_support"}
            ]
        )
        return [UserUtteranceReverted()]


class ActionExplainTransferForm(Action):
    """Explique pourquoi le formulaire demande le slot courant."""

    def name(self) -> Text:
        return "action_explain_transfer_form"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:

        requested_slot = tracker.get_slot("requested_slot")

        explanations = {
            "transfer_type": "J'ai besoin de savoir si vous envoyez vers un wallet Neero ou via Mobile Money pour router votre transfert correctement.",
            "amount": "J'ai besoin du montant que vous souhaitez envoyer pour preparer votre transfert.",
            "neero_id": "J'ai besoin du username Neero (format @username) du destinataire pour lui envoyer les fonds.",
            "phone_number": "J'ai besoin du numero de telephone du destinataire pour le transfert Mobile Money.",
        }

        explanation = explanations.get(
            requested_slot,
            "J'ai besoin de cette information pour completer votre transfert."
        )
        dispatcher.utter_message(text=explanation)
        return []


