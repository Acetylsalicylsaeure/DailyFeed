{ pkgs, ... }:
{
  # Python package and version specification
  packages = with pkgs; [ 
    sqlitebrowser
    python311
    python311Packages.pip
    python311Packages.virtualenv
  ];

  # Define Python-specific environment variables
  env = {
    PYTHONPATH = "${pkgs.python311Packages.pip}/lib/python3.11/site-packages";
  };

  # Add Python scripts to the PATH
  enterShell = ''
    echo "Python development environment activated!"
    python --version
  '';

  # For additional Python packages
  languages.python = {
    enable = true;
    package = pkgs.python311;
    venv = {
      enable = true;
      requirements = "./requirements.txt";
    };
  };
}
