import sys

try:
    import PyOpenColorIO as OCIO

    config = OCIO.GetCurrentConfig()

    # Try to get a processor for a basic conversion
    # We need valid spaces. Let's find some.
    spaces = config.getColorSpaceNames()
    if not spaces:
        print("No color spaces found in config")
        sys.exit(0)

    input_space = spaces[0]
    output_space = spaces[0]  # Just for testing

    print(f"Testing Processor with: {input_space} -> {output_space}")
    processor = config.getProcessor(input_space, output_space)
    print(f"Processor type: {type(processor)}")

    processor_methods = [m for m in dir(processor) if not m.startswith("_")]
    print("\nProcessor methods:")
    for m in sorted(processor_methods):
        print(f"  - {m}")

    if hasattr(processor, "getDefaultCPUProcessor"):
        cpu_processor = processor.getDefaultCPUProcessor()
        print(f"\nCPU Processor type: {type(cpu_processor)}")
        cpu_methods = [m for m in dir(cpu_processor) if not m.startswith("_")]
        print("\nCPU Processor methods:")
        for m in sorted(cpu_methods):
            print(f"  - {m}")
    else:
        print("\n❌ Processor has no getDefaultCPUProcessor")

except Exception as e:
    print(f"Error during processor inspection: {e}")
