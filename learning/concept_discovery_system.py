"""
Concept Discovery - Invent New Problem-Solving Approaches
Advanced concept discovery and creative problem-solving capabilities.
"""

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pathlib import Path
from loguru import logger

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    logger.warning("NumPy not available - some features limited")


class ConceptDiscoverySystem:
    """
    Concept discovery system for inventing new approaches:
    - Novel solution generation
    - Pattern recognition and abstraction
    - Concept combination and synthesis
    - Creative problem-solving
    - Innovation and invention
    """

    def __init__(self, config_path: str = "./config/settings.json"):
        """Initialize concept discovery system."""
        
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)
        
        self.discovery_path = Path("data/concept_discovery")
        self.discovery_path.mkdir(parents=True, exist_ok=True)
        
        self.discovered_concepts = self._load_discovered_concepts()
        self.pattern_library = self._load_pattern_library()
        self.innovation_history = self._load_innovation_history()
        
        logger.info("Concept Discovery System initialized")

    def _load_discovered_concepts(self) -> List[Dict[str, Any]]:
        """Load discovered concepts from storage."""
        concepts_path = self.discovery_path / "discovered_concepts.json"
        if concepts_path.exists():
            try:
                with open(concepts_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("Failed to load discovered concepts: {}", str(e))
        return []

    def _load_pattern_library(self) -> List[Dict[str, Any]]:
        """Load pattern library from storage."""
        patterns_path = self.discovery_path / "pattern_library.json"
        if patterns_path.exists():
            try:
                with open(patterns_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("Failed to load pattern library: {}", str(e))
        return self._initialize_pattern_library()

    def _load_innovation_history(self) -> List[Dict[str, Any]]:
        """Load innovation history from storage."""
        history_path = self.discovery_path / "innovation_history.json"
        if history_path.exists():
            try:
                with open(history_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("Failed to load innovation history: {}", str(e))
        return []

    def _initialize_pattern_library(self) -> List[Dict[str, Any]]:
        """Initialize default pattern library."""
        return [
            {
                "id": "pattern_1",
                "name": "Sequential Decomposition",
                "type": "problem_solving",
                "description": "Break complex problems into sequential steps",
                "applicability": ["planning", "task_decomposition"],
                "success_rate": 0.85
            },
            {
                "id": "pattern_2",
                "name": "Parallel Execution",
                "type": "optimization",
                "description": "Execute independent tasks in parallel",
                "applicability": ["task_execution", "performance"],
                "success_rate": 0.78
            },
            {
                "id": "pattern_3",
                "name": "Hierarchical Abstraction",
                "type": "reasoning",
                "description": "Use hierarchical abstraction for complex reasoning",
                "applicability": ["analysis", "planning"],
                "success_rate": 0.82
            }
        ]

    def _save_discovered_concepts(self):
        """Save discovered concepts to storage."""
        try:
            concepts_path = self.discovery_path / "discovered_concepts.json"
            with open(concepts_path, "w", encoding="utf-8") as f:
                json.dump(self.discovered_concepts, f, indent=2)
        except Exception as e:
            logger.error("Failed to save discovered concepts: {}", str(e))

    def _save_pattern_library(self):
        """Save pattern library to storage."""
        try:
            patterns_path = self.discovery_path / "pattern_library.json"
            with open(patterns_path, "w", encoding="utf-8") as f:
                json.dump(self.pattern_library, f, indent=2)
        except Exception as e:
            logger.error("Failed to save pattern library: {}", str(e))

    def _save_innovation_history(self):
        """Save innovation history to storage."""
        try:
            history_path = self.discovery_path / "innovation_history.json"
            with open(history_path, "w", encoding="utf-8") as f:
                json.dump(self.innovation_history, f, indent=2)
        except Exception as e:
            logger.error("Failed to save innovation history: {}", str(e))

    def discover_new_concept(
        self,
        problem_domain: str,
        current_approaches: List[str],
        constraints: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Discover a new concept for solving problems in a domain."""
        
        try:
            # Analyze current approaches
            approach_analysis = self._analyze_approaches(current_approaches)
            
            # Identify gaps and opportunities
            opportunities = self._identify_opportunities(approach_analysis, problem_domain)
            
            # Generate novel concepts
            novel_concepts = self._generate_novel_concepts(problem_domain, opportunities)
            
            # Evaluate concepts
            evaluated_concepts = self._evaluate_concepts(novel_concepts, constraints)
            
            # Select best concept
            best_concept = max(evaluated_concepts, key=lambda x: x.get("innovation_score", 0.0))
            
            # Add to discovered concepts
            best_concept["id"] = str(uuid.uuid4())
            best_concept["discovered_at"] = datetime.now().isoformat()
            best_concept["domain"] = problem_domain
            best_concept["status"] = "proposed"
            
            self.discovered_concepts.append(best_concept)
            self._save_discovered_concepts()
            
            # Record in innovation history
            self.innovation_history.append({
                "concept_id": best_concept["id"],
                "domain": problem_domain,
                "innovation_score": best_concept["innovation_score"],
                "timestamp": datetime.now().isoformat()
            })
            self._save_innovation_history()
            
            return {
                "success": True,
                "discovered_concept": best_concept,
                "alternative_concepts": evaluated_concepts,
                "message": f"Discovered new concept: {best_concept['name']}"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Concept discovery failed: {str(e)}"
            }

    def _analyze_approaches(self, approaches: List[str]) -> Dict[str, Any]:
        """Analyze current approaches to identify patterns."""
        
        approach_analysis = {
            "total_approaches": len(approaches),
            "diversity": len(set(approaches)) / len(approaches) if approaches else 0.0,
            "complexity": np.mean([len(approach.split()) for approach in approaches]) if approaches else 0.0,
            "common_patterns": self._extract_common_patterns(approaches)
        }
        
        return approach_analysis

    def _extract_common_patterns(self, approaches: List[str]) -> List[str]:
        """Extract common patterns from approaches."""
        
        # Simple pattern extraction based on word frequency
        word_counts = {}
        for approach in approaches:
            words = approach.lower().split()
            for word in words:
                word_counts[word] = word_counts.get(word, 0) + 1
        
        # Get most common words
        common_words = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        return [word for word, count in common_words]

    def _identify_opportunities(
        self,
        approach_analysis: Dict[str, Any],
        domain: str
    ) -> List[Dict[str, Any]]:
        """Identify opportunities for innovation."""
        
        opportunities = []
        
        # Low diversity suggests opportunity for novel approaches
        if approach_analysis["diversity"] < 0.5:
            opportunities.append({
                "type": "diversity_opportunity",
                "description": "Current approaches lack diversity - explore new paradigms",
                "potential_impact": 0.8
            })
        
        # High complexity suggests opportunity for simplification
        if approach_analysis["complexity"] > 10:
            opportunities.append({
                "type": "simplification_opportunity",
                "description": "Current approaches are complex - develop simpler solutions",
                "potential_impact": 0.7
            })
        
        # Domain-specific opportunities
        domain_opportunities = self._get_domain_opportunities(domain)
        opportunities.extend(domain_opportunities)
        
        return opportunities

    def _get_domain_opportunities(self, domain: str) -> List[Dict[str, Any]]:
        """Get domain-specific innovation opportunities."""
        
        domain_opportunities = {
            "planning": [
                {"type": "temporal_reasoning", "description": "Incorporate temporal reasoning", "potential_impact": 0.7},
                {"type": "resource_optimization", "description": "Optimize resource allocation", "potential_impact": 0.8}
            ],
            "execution": [
                {"type": "parallel_processing", "description": "Implement parallel execution", "potential_impact": 0.9},
                {"type": "adaptive_scheduling", "description": "Develop adaptive scheduling", "potential_impact": 0.8}
            ],
            "learning": [
                {"type": "meta_learning", "description": "Implement meta-learning", "potential_impact": 0.9},
                {"type": "transfer_learning", "description": "Utilize transfer learning", "potential_impact": 0.8}
            ]
        }
        
        return domain_opportunities.get(domain, [])

    def _generate_novel_concepts(
        self,
        domain: str,
        opportunities: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Generate novel concepts based on opportunities."""
        
        novel_concepts = []
        
        for opportunity in opportunities:
            concept = {
                "name": f"Novel {opportunity['type']} approach",
                "type": opportunity["type"],
                "description": opportunity["description"],
                "domain": domain,
                "novelty_score": (np.random.uniform(0.6, 0.9) if NUMPY_AVAILABLE else 0.75),
                "feasibility_score": (np.random.uniform(0.5, 0.8) if NUMPY_AVAILABLE else 0.65),
                "potential_impact": opportunity.get("potential_impact", 0.7)
            }
            novel_concepts.append(concept)
        
        return novel_concepts

    def _evaluate_concepts(
        self,
        concepts: List[Dict[str, Any]],
        constraints: Optional[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Evaluate concepts based on multiple criteria."""
        
        evaluated_concepts = []
        
        for concept in concepts:
            # Calculate innovation score
            innovation_score = (
                concept.get("novelty_score", 0.5) * 0.4 +
                concept.get("feasibility_score", 0.5) * 0.3 +
                concept.get("potential_impact", 0.5) * 0.3
            )
            
            concept["innovation_score"] = innovation_score
            
            # Apply constraints if provided
            if constraints:
                constraint_satisfaction = self._check_constraints(concept, constraints)
                concept["constraint_satisfaction"] = constraint_satisfaction
                innovation_score *= constraint_satisfaction
            
            evaluated_concepts.append(concept)
        
        return evaluated_concepts

    def _check_constraints(
        self,
        concept: Dict[str, Any],
        constraints: Dict[str, Any]
    ) -> float:
        """Check how well a concept satisfies constraints."""
        
        satisfaction = 1.0
        
        # Resource constraints
        if "max_complexity" in constraints:
            if concept.get("novelty_score", 0.5) > constraints["max_complexity"]:
                satisfaction *= 0.8
        
        # Time constraints
        if "max_development_time" in constraints:
            if concept.get("feasibility_score", 0.5) < 0.5:
                satisfaction *= 0.7
        
        return satisfaction

    def combine_concepts(
        self,
        concept_ids: List[str],
        combination_strategy: str = "synthesis"
    ) -> Dict[str, Any]:
        """Combine multiple concepts to create new approaches."""
        
        try:
            # Get concepts
            concepts = [c for c in self.discovered_concepts if c["id"] in concept_ids]
            
            if len(concepts) < 2:
                return {
                    "success": False,
                    "error": "At least 2 concepts required for combination"
                }
            
            # Combine based on strategy
            if combination_strategy == "synthesis":
                combined_concept = self._synthesize_concepts(concepts)
            elif combination_strategy == "integration":
                combined_concept = self._integrate_concepts(concepts)
            elif combination_strategy == "abstraction":
                combined_concept = self._abstract_concepts(concepts)
            else:
                return {
                    "success": False,
                    "error": f"Unknown combination strategy: {combination_strategy}"
                }
            
            # Add to discovered concepts
            combined_concept["id"] = str(uuid.uuid4())
            combined_concept["combined_from"] = concept_ids
            combined_concept["combination_strategy"] = combination_strategy
            combined_concept["discovered_at"] = datetime.now().isoformat()
            combined_concept["status"] = "proposed"
            
            self.discovered_concepts.append(combined_concept)
            self._save_discovered_concepts()
            
            return {
                "success": True,
                "combined_concept": combined_concept,
                "source_concepts": concepts,
                "message": f"Combined {len(concepts)} concepts using {combination_strategy}"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Concept combination failed: {str(e)}"
            }

    def _synthesize_concepts(self, concepts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Synthesize concepts by merging their strengths."""
        
        combined_name = " + ".join([c["name"] for c in concepts])
        combined_description = f"Synthesis of: {', '.join([c['description'] for c in concepts])}"
        
        return {
            "name": combined_name,
            "type": "synthesis",
            "description": combined_description,
            "novelty_score": (np.mean([c.get("novelty_score", 0.5) for c in concepts]) * 1.1 if NUMPY_AVAILABLE else 0.75),
            "feasibility_score": np.mean([c.get("feasibility_score", 0.5) for c in concepts]) * 0.9,
            "potential_impact": np.mean([c.get("potential_impact", 0.5) for c in concepts]) * 1.2
        }

    def _integrate_concepts(self, concepts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Integrate concepts by creating a unified approach."""
        
        combined_name = "Integrated " + " & ".join([c["type"] for c in concepts])
        combined_description = f"Integrated approach combining: {', '.join([c['name'] for c in concepts])}"
        
        return {
            "name": combined_name,
            "type": "integration",
            "description": combined_description,
            "novelty_score": (np.mean([c.get("novelty_score", 0.5) for c in concepts]) * 0.8 if NUMPY_AVAILABLE else 0.65),
            "feasibility_score": np.mean([c.get("feasibility_score", 0.5) for c in concepts]) * 1.1,
            "potential_impact": np.mean([c.get("potential_impact", 0.5) for c in concepts]) * 1.3
        }

    def _abstract_concepts(self, concepts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Abstract concepts to create higher-level approaches."""
        
        combined_name = "Abstract " + " Framework"
        combined_description = f"Abstract framework derived from: {', '.join([c['name'] for c in concepts])}"
        
        return {
            "name": combined_name,
            "type": "abstraction",
            "description": combined_description,
            "novelty_score": (np.mean([c.get("novelty_score", 0.5) for c in concepts]) * 1.3 if NUMPY_AVAILABLE else 0.85),
            "feasibility_score": np.mean([c.get("feasibility_score", 0.5) for c in concepts]) * 0.7,
            "potential_impact": np.mean([c.get("potential_impact", 0.5) for c in concepts]) * 1.1
        }

    def recognize_patterns(
        self,
        data_points: List[Dict[str, Any]],
        pattern_type: str = "general"
    ) -> Dict[str, Any]:
        """Recognize patterns in data for insight generation."""
        
        try:
            # Extract features from data
            features = self._extract_features(data_points)
            
            # Detect patterns based on type
            if pattern_type == "temporal":
                patterns = self._detect_temporal_patterns(data_points)
            elif pattern_type == "sequential":
                patterns = self._detect_sequential_patterns(data_points)
            elif pattern_type == "hierarchical":
                patterns = self._detect_hierarchical_patterns(data_points)
            else:
                patterns = self._detect_general_patterns(features)
            
            # Add to pattern library
            for pattern in patterns:
                pattern["id"] = str(uuid.uuid4())
                pattern["discovered_at"] = datetime.now().isoformat()
                pattern["pattern_type"] = pattern_type
                self.pattern_library.append(pattern)
            
            self._save_pattern_library()
            
            return {
                "success": True,
                "recognized_patterns": patterns,
                "total_patterns": len(patterns),
                "message": f"Recognized {len(patterns)} patterns"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Pattern recognition failed: {str(e)}"
            }

    def _extract_features(self, data_points: List[Dict[str, Any]]) -> Dict[str, List[float]]:
        """Extract features from data points."""
        
        features = {}
        
        for key in data_points[0].keys():
            if isinstance(data_points[0][key], (int, float)):
                features[key] = [dp[key] for dp in data_points]
        
        return features

    def _detect_temporal_patterns(self, data_points: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Detect temporal patterns in data."""
        
        patterns = []
        
        # Check for trends
        if len(data_points) > 3:
            values = [dp.get("value", 0) for dp in data_points if "value" in dp]
            if values:
                trend = np.polyfit(range(len(values)), values, 1)[0]
                if abs(trend) > 0.1:
                    patterns.append({
                        "name": "Trend Pattern",
                        "description": f"{'Increasing' if trend > 0 else 'Decreasing'} trend detected",
                        "strength": abs(trend),
                        "type": "temporal"
                    })
        
        return patterns

    def _detect_sequential_patterns(self, data_points: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Detect sequential patterns in data."""
        
        patterns = []
        
        # Check for repeating sequences
        if len(data_points) > 5:
            sequences = {}
            for i in range(len(data_points) - 2):
                sequence = tuple(dp.get("action", "unknown") for dp in data_points[i:i+3])
                sequences[sequence] = sequences.get(sequence, 0) + 1
            
            for sequence, count in sequences.items():
                if count > 1:
                    patterns.append({
                        "name": "Repeating Sequence",
                        "description": f"Sequence {' -> '.join(sequence)} repeats {count} times",
                        "frequency": count / len(data_points),
                        "type": "sequential"
                    })
        
        return patterns

    def _detect_hierarchical_patterns(self, data_points: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Detect hierarchical patterns in data."""
        
        patterns = []
        
        # Check for parent-child relationships
        parent_child_pairs = {}
        for dp in data_points:
            if "parent" in dp and "child" in dp:
                pair = (dp["parent"], dp["child"])
                parent_child_pairs[pair] = parent_child_pairs.get(pair, 0) + 1
        
        for pair, count in parent_child_pairs.items():
            if count > 1:
                patterns.append({
                    "name": "Hierarchical Relationship",
                    "description": f"Parent-child relationship {pair[0]} -> {pair[1]}",
                    "frequency": count,
                    "type": "hierarchical"
                })
        
        return patterns

    def _detect_general_patterns(self, features: Dict[str, List[float]]) -> List[Dict[str, Any]]:
        """Detect general patterns in features."""
        
        patterns = []
        
        for feature_name, values in features.items():
            # Check for clusters
            if len(values) > 3:
                mean_val = np.mean(values)
                std_val = np.std(values)
                
                if std_val > 0:
                    patterns.append({
                        "name": f"{feature_name} Distribution",
                        "description": f"Mean: {mean_val:.2f}, Std: {std_val:.2f}",
                        "type": "distribution"
                    })
        
        return patterns

    def generate_creative_solution(
        self,
        problem_description: str,
        domain: str,
        creativity_level: float = 0.8
    ) -> Dict[str, Any]:
        """Generate a creative solution for a problem."""
        
        try:
            # Analyze problem
            problem_analysis = self._analyze_problem(problem_description)
            
            # Generate solution approaches
            solution_approaches = self._generate_solution_approaches(problem_analysis, domain)
            
            # Apply creativity level
            creative_solutions = self._apply_creativity(solution_approaches, creativity_level)
            
            # Select best creative solution
            best_solution = max(creative_solutions, key=lambda x: x.get("creativity_score", 0.0))
            
            return {
                "success": True,
                "creative_solution": best_solution,
                "alternative_solutions": creative_solutions,
                "problem_analysis": problem_analysis,
                "message": f"Generated creative solution: {best_solution['name']}"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Creative solution generation failed: {str(e)}"
            }

    def _analyze_problem(self, problem_description: str) -> Dict[str, Any]:
        """Analyze problem description."""
        
        # Simple analysis based on keyword extraction
        keywords = problem_description.lower().split()
        
        problem_analysis = {
            "complexity": len(keywords) / 20.0,  # Normalized complexity
            "domain_keywords": [kw for kw in keywords if len(kw) > 4],
            "action_verbs": [kw for kw in keywords if kw in ["solve", "fix", "improve", "optimize", "create", "design"]],
            "problem_type": self._classify_problem_type(keywords)
        }
        
        return problem_analysis

    def _classify_problem_type(self, keywords: List[str]) -> str:
        """Classify the type of problem."""
        
        if any(kw in keywords for kw in ["optim", "efficient", "fast", "quick"]):
            return "optimization"
        elif any(kw in keywords for kw in ["create", "design", "build", "develop"]):
            return "creation"
        elif any(kw in keywords for kw in ["fix", "solve", "resolve", "correct"]):
            return "problem_solving"
        else:
            return "general"

    def _generate_solution_approaches(
        self,
        problem_analysis: Dict[str, Any],
        domain: str
    ) -> List[Dict[str, Any]]:
        """Generate solution approaches based on problem analysis."""
        
        approaches = []
        
        # Generate approaches based on problem type
        problem_type = problem_analysis["problem_type"]
        
        if problem_type == "optimization":
            approaches.append({
                "name": "Algorithmic Optimization",
                "description": "Optimize algorithms for better performance",
                "approach_type": "algorithmic"
            })
            approaches.append({
                "name": "Resource Optimization",
                "description": "Optimize resource allocation and usage",
                "approach_type": "resource"
            })
        
        elif problem_type == "creation":
            approaches.append({
                "name": "Design-Based Creation",
                "description": "Use design principles for creation",
                "approach_type": "design"
            })
            approaches.append({
                "name": "Iterative Creation",
                "description": "Use iterative development approach",
                "approach_type": "iterative"
            })
        
        elif problem_type == "problem_solving":
            approaches.append({
                "name": "Analytical Problem Solving",
                "description": "Use analytical methods for problem solving",
                "approach_type": "analytical"
            })
            approaches.append({
                "name": "Heuristic Problem Solving",
                "description": "Use heuristic approaches for problem solving",
                "approach_type": "heuristic"
            })
        
        return approaches

    def _apply_creativity(
        self,
        approaches: List[Dict[str, Any]],
        creativity_level: float
    ) -> List[Dict[str, Any]]:
        """Apply creativity to solution approaches."""
        
        creative_approaches = []
        
        for approach in approaches:
            # Apply creativity modifiers
            creativity_multiplier = 1.0 + (creativity_level * 0.5)
            
            creative_approach = approach.copy()
            creative_approach["creativity_modifiers"] = {
                "novelty_boost": creativity_level * 0.3,
                "feasibility_adjustment": -creativity_level * 0.1,
                "impact_enhancement": creativity_level * 0.2
            }
            
            # Calculate creativity score
            creativity_score = (
                creativity_level * 0.5 +
                np.random.uniform(0.0, 0.5) * 0.3 +
                approach.get("approach_type", "general") == "innovative" * 0.2
            )
            
            creative_approach["creativity_score"] = creativity_score
            creative_approaches.append(creative_approach)
        
        return creative_approaches

    def get_discovery_summary(self) -> Dict[str, Any]:
        """Get concept discovery summary."""
        
        return {
            "success": True,
            "discovery_summary": {
                "total_discovered_concepts": len(self.discovered_concepts),
                "total_patterns": len(self.pattern_library),
                "total_innovations": len(self.innovation_history),
                "average_innovation_score": np.mean([c.get("innovation_score", 0.5) for c in self.discovered_concepts]) if self.discovered_concepts else 0.0,
                "concept_types": {
                    "synthesis": len([c for c in self.discovered_concepts if c.get("type") == "synthesis"]),
                    "integration": len([c for c in self.discovered_concepts if c.get("type") == "integration"]),
                    "abstraction": len([c for c in self.discovered_concepts if c.get("type") == "abstraction"])
                }
            },
            "message": "Discovery summary generated successfully"
        }