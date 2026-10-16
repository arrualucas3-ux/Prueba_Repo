// Explicitly decode the finite function seed list before read-only REA queries.
// @category RVJinx
import ghidra.app.script.GhidraScript;
import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.SourceType;
import java.nio.file.Files;
import java.nio.file.Path;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

public class RVPrepareFunctions extends GhidraScript {
    @Override public void run() throws Exception {
        JsonObject inventory=JsonParser.parseString(Files.readString(Path.of(getScriptArgs()[0]))).getAsJsonObject();
        int decoded=0;
        for (JsonElement element:inventory.getAsJsonArray("function_seeds")) {
            monitor.checkCancelled();
            JsonObject seed=element.getAsJsonObject();
            Address start=toAddr(seed.get("address").getAsString());
            Address end=toAddr(seed.get("decode_end_exclusive").getAsString()).subtract(1);
            DisassembleCommand command=new DisassembleCommand(start,new AddressSet(start,end),true);
            command.enableCodeAnalysis(false);
            if (!command.applyTo(currentProgram,monitor) || command.getDisassembledAddressSet().isEmpty()) {
                println("RV seed decode failed: "+start+" "+command.getStatusMsg());
                continue;
            }
            Function function=getFunctionAt(start);
            if (function==null) function=createFunction(start,null);
            if (function==null) throw new IllegalStateException("No function at "+start);
            function.setBody(new AddressSet(command.getDisassembledAddressSet()));
            if (seed.has("candidate_name")) function.setName(seed.get("candidate_name").getAsString(),SourceType.USER_DEFINED);
            decoded++;
        }
        println("RV explicitly decoded functions: "+decoded);
    }
}
