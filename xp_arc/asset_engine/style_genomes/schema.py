"""Style Genome schema and loader."""
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field
from enum import Enum


class OutputFormat(str, Enum):
    SVG = "svg"
    PNG = "png"
    PDF = "pdf"
    PSD = "psd"


class PostProcess(str, Enum):
    POTRACE_SVG = "potrace_svg_cleanup"
    UPSCALE_2X_BLEED = "upscale_2x_add_bleed"
    SPRITE_SHEET_SLICE = "sprite_sheet_slice"
    REMOVE_BG = "remove_background"
    VECTORIZE = "vectorize"
    NONE = "none"


class GenerationParams(BaseModel):
    sampler: str = "euler_a"
    steps: int = 30
    cfg_scale: float = 7.0
    width: int = 1024
    height: int = 1024
    aspect_ratio: str = "1:1"
    seed: int | None = None


class VariantConfig(BaseModel):
    id: str
    prompt_suffix: str = ""
    negative_suffix: str = ""
    output_format: OutputFormat = OutputFormat.PNG
    postprocess: PostProcess = PostProcess.NONE
    params_override: GenerationParams | None = None


class VisualDNA(BaseModel):
    line_weight: str = "medium"
    color_palette: list[str] = Field(default_factory=list)
    proportions: str = "standard"
    shading: str = "cel_shaded"
    background: str = "simple"


class EvolutionEntry(BaseModel):
    version: int
    note: str
    parent: int | None = None
    human_rating: float | None = None
    rating_notes: str = ""


class StyleGenome(BaseModel):
    style_id: str
    parent: str | None = None
    version: int = 1
    description: str = ""
    visual_dna: VisualDNA = VisualDNA()
    
    prompt_genome: dict = Field(default_factory=dict)
    # Structure:
    # positive_core: str
    # negative_core: str
    # parameters: GenerationParams
    
    variants: dict[str, VariantConfig] = Field(default_factory=dict)
    evolution_log: list[EvolutionEntry] = Field(default_factory=list)
    
    @classmethod
    def load(cls, path: Path) -> "StyleGenome":
        import yaml
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(**data)
    
    def save(self, path: Path):
        import yaml
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(self.model_dump(), f, sort_keys=False, default_flow_style=False)
    
    def get_prompt(self, variant_id: str, concept: str, theme: str) -> tuple[str, str]:
        """Generate positive and negative prompts for a variant."""
        variant = self.variants.get(variant_id)
        if not variant:
            raise ValueError(f"Variant {variant_id} not found in {self.style_id}")
        
        pos = self.prompt_genome.get("positive_core", "")
        neg = self.prompt_genome.get("negative_core", "")
        
        pos = pos.format(
            style_id=self.style_id,
            subject=concept,
            theme=theme
        )
        neg = neg.format(
            style_id=self.style_id,
            subject=concept,
            theme=theme
        )
        
        pos += " " + variant.prompt_suffix
        neg += " " + variant.negative_suffix
        
        return pos.strip(), neg.strip()
    
    def get_params(self, variant_id: str) -> GenerationParams:
        base = self.prompt_genome.get("parameters", GenerationParams())
        variant = self.variants.get(variant_id)
        if variant and variant.params_override:
            # Merge overrides
            return GenerationParams(
                **{**base.model_dump(), **variant.params_override.model_dump(exclude_unset=True)}
            )
        return base