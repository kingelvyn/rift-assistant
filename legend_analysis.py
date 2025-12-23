# legend_analysis.py - Legend ability integration

from typing import Optional, List, Dict, Tuple
from enum import Enum
from dataclasses import dataclass
from game_state import CardInHand, PlayerState, CardType, Rune, Unit, Battlefield
from card_db import CardRecord
from logger_config import advisor_logger, log_legend_interaction


class LegendSynergyType(str, Enum):
    """Types of legend synergies."""
    EXHAUSTION_COST = "exhaustion_cost"  # Card requires exhausting legend
    READY_EFFECT = "ready_effect"  # Card can ready legend
    DOMAIN_SYNERGY = "domain_synergy"  # Same domain benefits
    TRIBAL_SYNERGY = "tribal_synergy"  # Shares creature types/tags
    ACTIVATED_SUPPORT = "activated_support"  # Legend ability supports this card
    PASSIVE_BUFF = "passive_buff"  # Legend passive enhances card
    COMBO_ENABLER = "combo_enabler"  # Card enables legend combo
    COUNTER_RISK = "counter_risk"  # Opponent legend may counter this
    PROTECTION = "protection"  # Protects or benefits legend


@dataclass
class LegendSynergy:
    """Represents a synergy between a card and legend."""
    synergy_type: LegendSynergyType
    description: str
    value_modifier: float  # How much this affects card value (-1.0 to +5.0)
    is_opponent: bool = False  # Whether this is opponent's legend interaction
    requires_condition: Optional[str] = None  # Condition needed for synergy
    timing: str = "immediate"  # "immediate", "next_turn", "conditional"


@dataclass
class LegendAbilityEvaluation:
    """Evaluation of legend's current ability value."""
    legend_name: str
    can_activate: bool
    activated_abilities: List[str]
    passive_abilities: List[str]
    triggered_abilities: List[str]
    domain: Rune
    exhausted: bool
    recommended_action: Optional[str] = None
    value_score: float = 0.0


def requires_legend_exhaustion(card: CardInHand) -> bool:
    """Check if a card's rules text indicates it requires exhausting the legend."""
    if not card.rules_text:
        return False
    
    rules_lower = card.rules_text.lower()
    
    # Common patterns for legend exhaustion costs
    patterns = [
        "exhaust your legend as an additional cost",
        "exhaust your legend to",
        "you may exhaust your legend",
        "exhaust legend:"
    ]
    
    return any(pattern in rules_lower for pattern in patterns)


def can_exhaust_legend(player: PlayerState) -> bool:
    """Check if the player has a legend and it is not exhausted."""
    if player.legend is None:
        return False
    return not player.legend.exhausted


def card_references_legend(card: CardInHand, legend_name: str) -> bool:
    """Check if card explicitly mentions a legend by name."""
    if not card.rules_text or not legend_name:
        return False
    
    return legend_name.lower() in card.rules_text.lower()


def shares_domain(card: CardInHand, legend: 'Legend') -> bool:
    """Check if card shares domain with legend."""
    if not legend or not hasattr(legend, 'domain'):
        return False
    
    return card.domain == legend.domain


def shares_tags(card: CardInHand, legend: 'Legend') -> bool:
    """Check if card shares tribal tags with legend."""
    if not legend or not hasattr(legend, 'tags'):
        return False
    
    if not card.tags or not legend.tags:
        return False
    
    card_tags = {t.lower() for t in card.tags}
    legend_tags = {t.lower() for t in legend.tags}
    
    return bool(card_tags & legend_tags)


def analyze_exhaustion_synergy(
    card: CardInHand, 
    player: PlayerState
) -> Optional[LegendSynergy]:
    """Analyze synergies related to legend exhaustion."""
    
    if not player.legend:
        return None
    
    legend = player.legend
    rules_lower = card.rules_text.lower() if card.rules_text else ""
    
    # Card requires exhausting legend
    if requires_legend_exhaustion(card):
        if can_exhaust_legend(player):
            return LegendSynergy(
                synergy_type=LegendSynergyType.EXHAUSTION_COST,
                description=f"Can exhaust {legend.name or 'legend'} for enhanced effect",
                value_modifier=1.5,  # Bonus if we can exhaust
                requires_condition="Legend must be ready",
                timing="immediate"
            )
        else:
            return LegendSynergy(
                synergy_type=LegendSynergyType.EXHAUSTION_COST,
                description=f"BLOCKED: Requires exhausting {legend.name or 'legend'} (already exhausted)",
                value_modifier=-2.0,  # Penalty if we can't use the card
                requires_condition="Legend must be ready",
                timing="immediate"
            )
    
    # Card can ready the legend
    if "ready" in rules_lower and "legend" in rules_lower:
        if legend.exhausted:
            return LegendSynergy(
                synergy_type=LegendSynergyType.READY_EFFECT,
                description=f"Readies exhausted {legend.name or 'legend'} - enables second activation",
                value_modifier=3.0,  # Very valuable if legend is exhausted
                requires_condition="Legend must be exhausted",
                timing="immediate"
            )
        else:
            return LegendSynergy(
                synergy_type=LegendSynergyType.READY_EFFECT,
                description=f"Can ready {legend.name or 'legend'} (currently not exhausted)",
                value_modifier=0.5,  # Some value for future turns
                timing="next_turn"
            )
    
    return None


def analyze_domain_synergy(
    card: CardInHand, 
    player: PlayerState
) -> Optional[LegendSynergy]:
    """Analyze domain-based synergies."""
    
    if not player.legend:
        return None
    
    legend = player.legend
    
    # Check if legend has domain-specific abilities
    if legend.passive_abilities:
        for ability in legend.passive_abilities:
            ability_lower = ability.lower()
            
            # Check if ability benefits same-domain cards
            domain_name = card.domain.value if hasattr(card.domain, 'value') else str(card.domain)
            
            if domain_name.lower() in ability_lower:
                if shares_domain(card, legend):
                    return LegendSynergy(
                        synergy_type=LegendSynergyType.DOMAIN_SYNERGY,
                        description=f"{legend.name or 'Legend'} buffs {domain_name} cards - this card benefits",
                        value_modifier=2.0,
                        timing="immediate"
                    )
    
    # Check if card mentions domain synergy
    if card.rules_text:
        rules_lower = card.rules_text.lower()
        legend_domain = legend.domain.value if hasattr(legend.domain, 'value') else str(legend.domain)
        
        if legend_domain.lower() in rules_lower:
            return LegendSynergy(
                synergy_type=LegendSynergyType.DOMAIN_SYNERGY,
                description=f"Card references {legend_domain} - synergizes with your legend",
                value_modifier=1.5,
                timing="immediate"
            )
    
    return None


def analyze_tribal_synergy(
    card: CardInHand, 
    player: PlayerState
) -> Optional[LegendSynergy]:
    """Analyze tribal/tag-based synergies."""
    
    if not player.legend:
        return None
    
    legend = player.legend
    
    if shares_tags(card, legend):
        shared_tags = set(t.lower() for t in card.tags) & set(t.lower() for t in legend.tags)
        tags_str = ", ".join(shared_tags)
        
        return LegendSynergy(
            synergy_type=LegendSynergyType.TRIBAL_SYNERGY,
            description=f"Shares tribal synergy ({tags_str}) with {legend.name or 'legend'}",
            value_modifier=1.0,
            timing="immediate"
        )
    
    # Check if legend has tribal-specific abilities
    if legend.passive_abilities and card.tags:
        for ability in legend.passive_abilities:
            ability_lower = ability.lower()
            
            for tag in card.tags:
                if tag.lower() in ability_lower:
                    return LegendSynergy(
                        synergy_type=LegendSynergyType.TRIBAL_SYNERGY,
                        description=f"{legend.name or 'Legend'} buffs {tag} cards - this card benefits",
                        value_modifier=2.0,
                        timing="immediate"
                    )
    
    return None


def analyze_activated_ability_synergy(
    card: CardInHand, 
    player: PlayerState,
    battlefields: Optional[List[Battlefield]] = None
) -> Optional[LegendSynergy]:
    """Analyze how legend's activated abilities support this card."""
    
    if not player.legend or not player.legend.activated_abilities:
        return None
    
    legend = player.legend
    
    # Can't use activated abilities if exhausted
    if legend.exhausted:
        return None
    
    for ability in legend.activated_abilities:
        ability_lower = ability.lower()
        
        # Unit support abilities
        if card.card_type == CardType.UNIT:
            # Movement abilities
            if any(keyword in ability_lower for keyword in ['move', 'swap', 'reposition']):
                return LegendSynergy(
                    synergy_type=LegendSynergyType.ACTIVATED_SUPPORT,
                    description=f"{legend.name or 'Legend'} can reposition this unit strategically",
                    value_modifier=1.0,
                    requires_condition="Legend must be ready",
                    timing="next_turn"
                )
            
            # Buff abilities
            if any(keyword in ability_lower for keyword in ['buff', 'might', '+', 'strengthen']):
                return LegendSynergy(
                    synergy_type=LegendSynergyType.ACTIVATED_SUPPORT,
                    description=f"{legend.name or 'Legend'} can buff this unit",
                    value_modifier=1.5,
                    requires_condition="Legend must be ready",
                    timing="immediate"
                )
            
            # Protection abilities
            if any(keyword in ability_lower for keyword in ['protect', 'shield', 'guard', 'save']):
                return LegendSynergy(
                    synergy_type=LegendSynergyType.ACTIVATED_SUPPORT,
                    description=f"{legend.name or 'Legend'} can protect this unit",
                    value_modifier=1.2,
                    requires_condition="Legend must be ready",
                    timing="conditional"
                )
        
        # Spell support
        elif card.card_type == CardType.SPELL:
            # Spell cost reduction
            if 'cost' in ability_lower and any(word in ability_lower for word in ['reduce', 'less', 'discount']):
                return LegendSynergy(
                    synergy_type=LegendSynergyType.ACTIVATED_SUPPORT,
                    description=f"{legend.name or 'Legend'} can reduce spell costs",
                    value_modifier=1.0,
                    requires_condition="Legend must be ready",
                    timing="immediate"
                )
            
            # Spell copying
            if any(keyword in ability_lower for keyword in ['copy', 'duplicate', 'additional']):
                return LegendSynergy(
                    synergy_type=LegendSynergyType.ACTIVATED_SUPPORT,
                    description=f"{legend.name or 'Legend'} can copy spells - double value!",
                    value_modifier=2.5,
                    requires_condition="Legend must be ready",
                    timing="immediate"
                )
        
        # Gear support
        elif card.card_type == CardType.GEAR:
            if any(keyword in ability_lower for keyword in ['attach', 'equip', 'gear']):
                return LegendSynergy(
                    synergy_type=LegendSynergyType.ACTIVATED_SUPPORT,
                    description=f"{legend.name or 'Legend'} can help attach equipment",
                    value_modifier=0.8,
                    requires_condition="Legend must be ready",
                    timing="immediate"
                )
    
    return None


def analyze_passive_synergy(
    card: CardInHand, 
    player: PlayerState
) -> Optional[LegendSynergy]:
    """Analyze how legend's passive abilities benefit this card."""
    
    if not player.legend or not player.legend.passive_abilities:
        return None
    
    legend = player.legend
    
    for ability in legend.passive_abilities:
        ability_lower = ability.lower()
        
        # Unit buffs
        if card.card_type == CardType.UNIT:
            # Might buffs
            if any(keyword in ability_lower for keyword in ['might', '+1/', '+2/', 'stronger']):
                return LegendSynergy(
                    synergy_type=LegendSynergyType.PASSIVE_BUFF,
                    description=f"{legend.name or 'Legend'} passive buffs all units",
                    value_modifier=1.5,
                    timing="immediate"
                )
            
            # Keyword grants
            if any(keyword in ability_lower for keyword in ['assault', 'guard', 'flying', 'overwhelm']):
                return LegendSynergy(
                    synergy_type=LegendSynergyType.PASSIVE_BUFF,
                    description=f"{legend.name or 'Legend'} grants keywords to units",
                    value_modifier=1.2,
                    timing="immediate"
                )
        
        # Spell benefits
        elif card.card_type == CardType.SPELL:
            # Spell damage boost
            if any(keyword in ability_lower for keyword in ['spell damage', 'bonus damage', 'spells deal']):
                tags_lower = [t.lower() for t in (card.tags or [])]
                if any(t in tags_lower for t in ['damage', 'removal', 'destroy']):
                    return LegendSynergy(
                        synergy_type=LegendSynergyType.PASSIVE_BUFF,
                        description=f"{legend.name or 'Legend'} increases spell damage",
                        value_modifier=2.0,
                        timing="immediate"
                    )
            
            # Cost reduction
            if 'cost' in ability_lower and any(word in ability_lower for word in ['less', 'reduce']):
                return LegendSynergy(
                    synergy_type=LegendSynergyType.PASSIVE_BUFF,
                    description=f"{legend.name or 'Legend'} reduces spell costs passively",
                    value_modifier=1.5,
                    timing="immediate"
                )
    
    return None


def analyze_combo_potential(
    card: CardInHand, 
    player: PlayerState
) -> Optional[LegendSynergy]:
    """Analyze if this card enables legend combos."""
    
    if not player.legend:
        return None
    
    legend = player.legend
    
    # Check if card references legend by name
    if card_references_legend(card, legend.name or ""):
        return LegendSynergy(
            synergy_type=LegendSynergyType.COMBO_ENABLER,
            description=f"Directly references {legend.name} - key combo piece",
            value_modifier=3.0,
            timing="immediate"
        )
    
    # Check if card protects legend
    if card.rules_text:
        rules_lower = card.rules_text.lower()
        
        if 'legend' in rules_lower:
            # Protection effects
            if any(keyword in rules_lower for keyword in ['protect', 'prevent damage to', 'save']):
                return LegendSynergy(
                    synergy_type=LegendSynergyType.PROTECTION,
                    description=f"Protects {legend.name or 'legend'} from harm",
                    value_modifier=1.5,
                    timing="conditional"
                )
            
            # Sacrifice/cost effects
            if any(keyword in rules_lower for keyword in ['sacrifice', 'destroy', 'exile']) and 'legend' in rules_lower:
                # This is usually bad unless it's a combo
                if 'when' in rules_lower or 'if' in rules_lower:
                    return LegendSynergy(
                        synergy_type=LegendSynergyType.COMBO_ENABLER,
                        description=f"May have legend-based combo - review carefully",
                        value_modifier=0.0,
                        timing="conditional"
                    )
    
    return None


def analyze_opponent_legend_risk(
    card: CardInHand, 
    opponent: Optional[PlayerState]
) -> Optional[LegendSynergy]:
    """Analyze if opponent's legend poses risks to this play."""
    
    if not opponent or not opponent.legend:
        return None
    
    op_legend = opponent.legend
    
    # Check triggered abilities
    if op_legend.triggered_abilities:
        for ability in op_legend.triggered_abilities:
            ability_lower = ability.lower()
            
            # Unit removal triggers
            if card.card_type == CardType.UNIT:
                if any(keyword in ability_lower for keyword in ['destroy', 'kill', 'damage', 'remove']):
                    if 'when' in ability_lower or 'whenever' in ability_lower:
                        return LegendSynergy(
                            synergy_type=LegendSynergyType.COUNTER_RISK,
                            description=f"⚠️ {op_legend.name or 'Opponent legend'} may remove this unit on entry",
                            value_modifier=-1.0,
                            is_opponent=True,
                            timing="immediate"
                        )
            
            # Spell counters
            elif card.card_type == CardType.SPELL:
                if any(keyword in ability_lower for keyword in ['counter', 'negate', 'cancel']):
                    return LegendSynergy(
                        synergy_type=LegendSynergyType.COUNTER_RISK,
                        description=f"⚠️ {op_legend.name or 'Opponent legend'} may counter spells",
                        value_modifier=-1.5,
                        is_opponent=True,
                        timing="immediate"
                    )
    
    # Check passive abilities
    if op_legend.passive_abilities:
        for ability in op_legend.passive_abilities:
            ability_lower = ability.lower()
            
            # Damage passives
            if card.card_type == CardType.UNIT:
                if any(keyword in ability_lower for keyword in ['damage', 'hurt', 'ping']):
                    return LegendSynergy(
                        synergy_type=LegendSynergyType.COUNTER_RISK,
                        description=f"⚠️ {op_legend.name or 'Opponent legend'} passive may damage units",
                        value_modifier=-0.5,
                        is_opponent=True,
                        timing="immediate"
                    )
            
            # Cost increase
            if 'cost' in ability_lower and any(word in ability_lower for word in ['more', 'additional', 'increase']):
                return LegendSynergy(
                    synergy_type=LegendSynergyType.COUNTER_RISK,
                    description=f"⚠️ {op_legend.name or 'Opponent legend'} increases card costs",
                    value_modifier=-0.8,
                    is_opponent=True,
                    timing="immediate"
                )
    
    # Check activated abilities (if legend is ready)
    if not op_legend.exhausted and op_legend.activated_abilities:
        for ability in op_legend.activated_abilities:
            ability_lower = ability.lower()
            
            # Removal abilities
            if any(keyword in ability_lower for keyword in ['destroy', 'kill', 'bounce', 'return']):
                return LegendSynergy(
                    synergy_type=LegendSynergyType.COUNTER_RISK,
                    description=f"⚠️ {op_legend.name or 'Opponent legend'} can activate removal (ready)",
                    value_modifier=-1.2,
                    is_opponent=True,
                    requires_condition="Opponent legend must be ready",
                    timing="conditional"
                )
    
    return None


def analyze_legend_synergy(
    card: CardInHand, 
    player: PlayerState, 
    opponent: Optional[PlayerState] = None,
    battlefields: Optional[List[Battlefield]] = None
) -> Tuple[List[LegendSynergy], float]:
    """
    Comprehensive analysis of card-legend interactions.
    
    Returns:
        (synergies, total_value_modifier)
    """
    synergies: List[LegendSynergy] = []
    
    # Analyze all synergy types
    exhaustion = analyze_exhaustion_synergy(card, player)
    if exhaustion:
        synergies.append(exhaustion)
    
    domain = analyze_domain_synergy(card, player)
    if domain:
        synergies.append(domain)
    
    tribal = analyze_tribal_synergy(card, player)
    if tribal:
        synergies.append(tribal)
    
    activated = analyze_activated_ability_synergy(card, player, battlefields)
    if activated:
        synergies.append(activated)
    
    passive = analyze_passive_synergy(card, player)
    if passive:
        synergies.append(passive)
    
    combo = analyze_combo_potential(card, player)
    if combo:
        synergies.append(combo)
    
    # Opponent legend risks
    if opponent:
        risk = analyze_opponent_legend_risk(card, opponent)
        if risk:
            synergies.append(risk)
    
    # Calculate total value modifier
    total_modifier = sum(s.value_modifier for s in synergies)
    
    # Log synergies
    if synergies and player.legend:
        for synergy in synergies:
            log_legend_interaction(
                advisor_logger,
                card.card_id,
                player.legend.card_id if not synergy.is_opponent else (opponent.legend.card_id if opponent and opponent.legend else "unknown"),
                synergy.synergy_type.value,
                card_name=card.name,
                legend_name=player.legend.name if not synergy.is_opponent else (opponent.legend.name if opponent and opponent.legend else "Opponent")
            )
    
    return synergies, total_modifier


def evaluate_legend_state(player: PlayerState) -> LegendAbilityEvaluation:
    """
    Evaluate the current state and value of the player's legend.
    """
    if not player.legend:
        return LegendAbilityEvaluation(
            legend_name="No Legend",
            can_activate=False,
            activated_abilities=[],
            passive_abilities=[],
            triggered_abilities=[],
            domain=Rune.COLORLESS,
            exhausted=False,
            recommended_action=None,
            value_score=0.0
        )
    
    legend = player.legend
    can_activate = not legend.exhausted and len(legend.activated_abilities or []) > 0
    
    # Calculate legend value score
    value_score = 0.0
    
    # Passive abilities always add value
    value_score += len(legend.passive_abilities or []) * 2.0
    
    # Activated abilities add value if legend is ready
    if can_activate:
        value_score += len(legend.activated_abilities or []) * 3.0
    
    # Triggered abilities add value
    value_score += len(legend.triggered_abilities or []) * 1.5
    
    # Recommend action
    recommended_action = None
    if legend.exhausted:
        recommended_action = "Legend exhausted - look for ready effects or plan for next turn"
    elif can_activate:
        recommended_action = f"Legend ready - consider using {len(legend.activated_abilities)} available ability(ies)"
    
    return LegendAbilityEvaluation(
        legend_name=legend.name or "Unknown Legend",
        can_activate=can_activate,
        activated_abilities=legend.activated_abilities or [],
        passive_abilities=legend.passive_abilities or [],
        triggered_abilities=legend.triggered_abilities or [],
        domain=legend.domain,
        exhausted=legend.exhausted,
        recommended_action=recommended_action,
        value_score=value_score
    )


def format_legend_synergy_summary(synergies: List[LegendSynergy]) -> str:
    """Format synergies into a human-readable summary."""
    if not synergies:
        return "No legend synergies detected."
    
    # Group by type
    immediate = [s for s in synergies if s.timing == "immediate"]
    conditional = [s for s in synergies if s.timing == "conditional"]
    opponent = [s for s in synergies if s.is_opponent]
    
    parts = []
    
    if immediate:
        parts.append("Immediate: " + " | ".join(s.description for s in immediate))
    
    if conditional:
        parts.append("Conditional: " + " | ".join(s.description for s in conditional))
    
    if opponent:
        parts.append("Risks: " + " | ".join(s.description for s in opponent))
    
    return " • ".join(parts)