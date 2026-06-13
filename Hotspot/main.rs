use windows::Networking::Connectivity::NetworkInformation;
use windows::Networking::NetworkOperators::{
    NetworkOperatorTetheringManager, TetheringCapability, TetheringOperationalState,
};

type TOS = TetheringOperationalState;
type NOTM = NetworkOperatorTetheringManager;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let connection_profile = NetworkInformation::GetInternetConnectionProfile()?;
 
    let capability =
        NOTM::GetTetheringCapabilityFromConnectionProfile(&connection_profile)?;
    match capability {
        TetheringCapability::Enabled => {},
        _ => {
            println!("Error: Tethering Capability disabled.");
            return Ok(());
        }
    }

    let tethering_manager =
        NOTM::CreateFromConnectionProfile(&connection_profile)?;

    let current_state = tethering_manager.TetheringOperationalState()?;
    match current_state {
        TOS::Off => {
            println!("Activating Mobile Hotspot...");
            let result = 
                tethering_manager
                .StartTetheringAsync()?.get()?;
            println!("Operation status: {:?}", result.Status()?);
        },
        TOS::Unknown => println!("Unknown tethering operational state."),
        TOS::InTransition => println!("In a transitional state."),
        TOS::On => println!("Mobile Hotspot is already running."),
        _ => println!("Unknown state! {current_state:?}")
    }
    Ok(())
}
