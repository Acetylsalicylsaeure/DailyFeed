import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Dict, List, Tuple, Optional, Union
import os
import warnings


class ArticleRankingModel(nn.Module):
    """
    Neural network model for ranking RSS articles based on features and embeddings.
    
    The model processes two inputs:
    1. Numerical features from article metadata and engagement metrics
    2. Pre-computed article embeddings from a language model
    
    Both inputs are encoded to matching dimensions, concatenated, and processed
    through configurable hidden layers to predict user preference.
    """
    
    def __init__(
        self,
        feature_dim: int,
        embedding_dim: int,
        hidden_dim: int = 64,
        encoder_layers: int = 1,
        hidden_layers: int = 2,
        hidden_width_factor: float = 1.0,
        dropout_rate: float = 0.2
    ):
        """
        Initialize the article ranking model.
        
        Args:
            feature_dim: Dimension of the input feature vector
            embedding_dim: Dimension of the input article embedding
            hidden_dim: Dimension for the encoded representations
            encoder_layers: Number of layers in the encoders
            hidden_layers: Number of hidden layers after concatenation
            hidden_width_factor: Multiplier for width of hidden layers
            dropout_rate: Dropout probability for regularization
        """
        super().__init__()
        
        # Store configuration
        self.feature_dim = feature_dim
        self.embedding_dim = embedding_dim
        self.hidden_dim = hidden_dim
        self.dropout_rate = dropout_rate
        
        # Build feature encoder
        self.feature_encoder = self._build_encoder(
            input_dim=feature_dim,
            output_dim=hidden_dim,
            num_layers=encoder_layers
        )
        
        # Build embedding encoder
        self.embedding_encoder = self._build_encoder(
            input_dim=embedding_dim,
            output_dim=hidden_dim,
            num_layers=encoder_layers
        )
        
        # Concatenated dimension will be 2 * hidden_dim
        concat_dim = 2 * hidden_dim
        
        # Build hidden layers
        hidden_layers_list = []
        current_dim = concat_dim
        
        for i in range(hidden_layers):
            # Width decreases as we go deeper
            next_dim = int(hidden_dim * hidden_width_factor * (1 - 0.2 * i))
            next_dim = max(16, next_dim)  # Ensure minimum width
            
            hidden_layers_list.extend([
                nn.Linear(current_dim, next_dim),
                nn.ReLU(),
                nn.Dropout(dropout_rate)
            ])
            
            current_dim = next_dim
        
        self.hidden_layers = nn.Sequential(*hidden_layers_list) if hidden_layers_list else nn.Identity()
        
        # Output layer with tanh activation to get value between -1 and 1
        self.output_layer = nn.Linear(current_dim, 1)
    
    def _build_encoder(self, input_dim: int, output_dim: int, num_layers: int = 1) -> nn.Sequential:
        """
        Build an encoder network to transform input to the desired dimension.
        
        Args:
            input_dim: Input dimension
            output_dim: Output dimension
            num_layers: Number of layers in the encoder
            
        Returns:
            nn.Sequential: Encoder network
        """
        if num_layers <= 0:
            return nn.Linear(input_dim, output_dim)
        
        layers = []
        
        # First layer
        layers.append(nn.Linear(input_dim, output_dim))
        layers.append(nn.ReLU())
        
        # Additional layers
        for _ in range(num_layers - 1):
            layers.append(nn.Linear(output_dim, output_dim))
            layers.append(nn.ReLU())
        
        return nn.Sequential(*layers)
    
    def forward(self, features: torch.Tensor, embeddings: torch.Tensor) -> torch.Tensor:
        """
        Forward pass of the model.
        
        Args:
            features: Batch of feature vectors [batch_size, feature_dim]
            embeddings: Batch of article embeddings [batch_size, embedding_dim]
            
        Returns:
            torch.Tensor: Predicted preference scores [-1, 1]
        """
        # Encode features and embeddings to the same dimension
        encoded_features = self.feature_encoder(features)
        encoded_embeddings = self.embedding_encoder(embeddings)
        
        # Concatenate encoded representations
        concat = torch.cat([encoded_features, encoded_embeddings], dim=1)
        
        # Process through hidden layers
        hidden = self.hidden_layers(concat)
        
        # Get output prediction
        output = self.output_layer(hidden)
        
        # Apply tanh to get values in [-1, 1] range
        return torch.tanh(output)


class LightweightRankingModel(nn.Module):
    """
    Memory-efficient version of the article ranking model, optimized for resource-constrained
    environments. Uses fewer parameters and more efficient operations.
    """
    
    def __init__(
        self,
        feature_dim: int,
        embedding_dim: int,
        hidden_dim: int = 32,
        dropout_rate: float = 0.1
    ):
        """
        Initialize the lightweight article ranking model.
        
        Args:
            feature_dim: Dimension of the input feature vector
            embedding_dim: Dimension of the input article embedding
            hidden_dim: Dimension for the encoded representations
            dropout_rate: Dropout probability for regularization
        """
        super().__init__()
        
        # Simple feature encoder
        self.feature_encoder = nn.Sequential(
            nn.Linear(feature_dim, hidden_dim),
            nn.ReLU()
        )
        
        # Simple embedding encoder with dimension reduction
        self.embedding_encoder = nn.Sequential(
            nn.Linear(embedding_dim, hidden_dim),
            nn.ReLU()
        )
        
        # Combined processing with a single hidden layer
        self.hidden_layer = nn.Sequential(
            nn.Linear(2 * hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout_rate)
        )
        
        # Output layer
        self.output_layer = nn.Linear(hidden_dim, 1)
    
    def forward(self, features: torch.Tensor, embeddings: torch.Tensor) -> torch.Tensor:
        """
        Forward pass of the lightweight model.
        
        Args:
            features: Batch of feature vectors [batch_size, feature_dim]
            embeddings: Batch of article embeddings [batch_size, embedding_dim]
            
        Returns:
            torch.Tensor: Predicted preference scores [-1, 1]
        """
        # Encode inputs
        encoded_features = self.feature_encoder(features)
        encoded_embeddings = self.embedding_encoder(embeddings)
        
        # Concatenate
        concat = torch.cat([encoded_features, encoded_embeddings], dim=1)
        
        # Process through hidden layer
        hidden = self.hidden_layer(concat)
        
        # Get output
        output = self.output_layer(hidden)
        
        return torch.tanh(output)


def create_model(config: Dict) -> nn.Module:
    """
    Factory function to create a model based on configuration.
    
    Args:
        config: Dictionary with model configuration
            Required keys:
                - feature_dim: Dimension of feature vectors
                - embedding_dim: Dimension of article embeddings
            Optional keys:
                - model_type: 'standard' or 'lightweight'
                - hidden_dim: Dimension of hidden layers
                - encoder_layers: Number of encoder layers
                - hidden_layers: Number of hidden layers
                - hidden_width_factor: Factor for hidden layer width
                - dropout_rate: Dropout probability
    
    Returns:
        nn.Module: The configured model
    """
    model_type = config.get('model_type', 'standard')
    
    if model_type == 'lightweight':
        return LightweightRankingModel(
            feature_dim=config['feature_dim'],
            embedding_dim=config['embedding_dim'],
            hidden_dim=config.get('hidden_dim', 32),
            dropout_rate=config.get('dropout_rate', 0.1)
        )
    else:
        return ArticleRankingModel(
            feature_dim=config['feature_dim'],
            embedding_dim=config['embedding_dim'],
            hidden_dim=config.get('hidden_dim', 64),
            encoder_layers=config.get('encoder_layers', 1),
            hidden_layers=config.get('hidden_layers', 2),
            hidden_width_factor=config.get('hidden_width_factor', 1.0),
            dropout_rate=config.get('dropout_rate', 0.2)
        )



def save_model(model: nn.Module, filepath: str, save_full_model: bool = False) -> None:
    """
    Save model to a file.
    
    Args:
        model: PyTorch model to save
        filepath: Path where the model will be saved
        save_full_model: If True, saves the entire model object using pickle.
                        If False (default), saves only the state dictionary.
    """
    # Create directory if it doesn't exist
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    
    if save_full_model:
        # Save the entire model - uses pickle internally
        # Warning: this approach is less robust to code changes
        warnings.warn(
            "Saving full model with pickle. This may cause compatibility issues "
            "if model definition changes. Consider using save_full_model=False instead.",
            UserWarning
        )
        torch.save(model, filepath)
    else:
        # Save just the model parameters (recommended approach)
        # Save model configuration along with state dict for easier loading
        if isinstance(model, ArticleRankingModel):
            config = {
                'model_type': 'standard',
                'feature_dim': model.feature_dim,
                'embedding_dim': model.embedding_dim,
                'hidden_dim': model.hidden_dim,
                'dropout_rate': model.dropout_rate,
                # Count number of encoder layers by inspecting the module
                'encoder_layers': len([m for m in model.feature_encoder if isinstance(m, nn.Linear)]),
                # Count hidden layers
                'hidden_layers': len([m for m in model.hidden_layers if isinstance(m, nn.Linear)])
            }
        elif isinstance(model, LightweightRankingModel):
            config = {
                'model_type': 'lightweight',
                'feature_dim': model.feature_encoder[0].in_features,
                'embedding_dim': model.embedding_encoder[0].in_features,
                'hidden_dim': model.feature_encoder[0].out_features,
                'dropout_rate': model.hidden_layer[-1].p if isinstance(model.hidden_layer[-1], nn.Dropout) else 0.1
            }
        else:
            raise TypeError(f"Unsupported model type: {type(model)}")
        
        # Save both state dict and config in one file
        save_dict = {
            'state_dict': model.state_dict(),
            'config': config
        }
        torch.save(save_dict, filepath)
    
    print(f"Model saved to {filepath}")


def load_model(filepath: str, map_location: Optional[str] = None) -> nn.Module:
    """
    Load model from a file.
    
    Args:
        filepath: Path to the saved model file
        map_location: Optional device mapping (e.g., 'cpu', 'cuda')
    
    Returns:
        nn.Module: The loaded model
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Model file not found: {filepath}")
    
    # Load the saved file
    checkpoint = torch.load(filepath, map_location=map_location)
    
    # Check if this is a full model or just state_dict
    if isinstance(checkpoint, dict) and 'state_dict' in checkpoint and 'config' in checkpoint:
        # This is a state_dict save with config
        config = checkpoint['config']
        model = create_model(config)
        model.load_state_dict(checkpoint['state_dict'])
        print(f"Model loaded from {filepath} using state dictionary approach")
    else:
        # This is a full model save (using pickle)
        warnings.warn(
            "Loading full model with pickle. This may cause issues if the model definition "
            "has changed since saving.",
            UserWarning
        )
        model = checkpoint
        print(f"Model loaded from {filepath} using full model (pickle) approach")
    
    return model



# Example usage
if __name__ == "__main__":
    # Example configuration
    config = {
        'feature_dim': 9,         # Typical feature dimension from dataset
        'embedding_dim': 384,      # E5-small embedding dimension
        'model_type': 'standard',  # 'standard' or 'lightweight'
        'hidden_dim': 64,
        'encoder_layers': 1,
        'hidden_layers': 2,
        'hidden_width_factor': 1.0,
        'dropout_rate': 0.2
    }
    
    # Create model
    model = create_model(config)
    
    # Print model summary
    print(model)
    
    # Count parameters
    total_params = sum(p.numel() for p in model.parameters())
    print(f"Total parameters: {total_params:,}")
    
    # Example input
    features = torch.randn(16, config['feature_dim'])      # Batch of 16 feature vectors
    embeddings = torch.randn(16, config['embedding_dim'])  # Batch of 16 embeddings
    
    # Forward pass
    output = model(features, embeddings)
    print(f"Output shape: {output.shape}")
    print(f"Output range: {output.min().item():.4f} to {output.max().item():.4f}")


        # Example configuration
    config = {
        'feature_dim': 9,
        'embedding_dim': 384,
        'model_type': 'standard',
        'hidden_dim': 64,
        'encoder_layers': 1,
        'hidden_layers': 2,
        'dropout_rate': 0.2
    }
    
    # Create and save model
    model = create_model(config)
    
    # Example inputs
    features = torch.randn(16, config['feature_dim'])
    embeddings = torch.randn(16, config['embedding_dim'])
    
    # Get predictions before saving
    model.eval()
    with torch.no_grad():
        predictions_before = model(features, embeddings)
    
    # Save model (state dict approach - recommended)
    save_model(model, "test_models/article_ranking_model.pt")
    
    # Save model (full model approach - pickle)
    save_model(model, "test_models/article_ranking_model_full.pt", save_full_model=True)
    
    # Load model (state dict approach)
    loaded_model = load_model("test_models/article_ranking_model.pt")
    
    # Get predictions after loading
    loaded_model.eval()
    with torch.no_grad():
        predictions_after = loaded_model(features, embeddings)
    
    # Verify predictions are the same
    print(f"Max difference in predictions: {(predictions_before - predictions_after).abs().max().item()}")
    # Should be very close to 0
