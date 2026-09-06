# Sibelius Connect

> Source: *Sibelius ManuScript Language Guide*, Sibelius 2024.8, Chapter 6 ("Sibelius Connect"), PDF pages 178–180 (printed pages clxxviii–clxxx).
> https://resources.avid.com/SupportFiles/Sibelius/2024.8/ManuScript_Language_Guide.pdf

Using Sibelius Connect, you can remotely control Sibelius by using apps running locally or from a mobile device or tablet. Sibelius Connect lets third-party developers create apps to control Sibelius over localhost using ManuScript command IDs.

## User Interface

You can enable (or disable) the remote control feature by going to the Input Devices page of the Preferences dialog. The network port used for the websocket connection is 1898 by default, but can be overridden with any value between 1025 and 65535.

## Websocket Connection

The websocket connection URL is `ws://127.0.0.1:1898` (by default) and is left unsecure. You can test it using a simple web browser. The PieSocket Websocket tester Chrome extension has been found to work for this.

Sibelius only accepts a connection originating from an application running on the same host (such as the Stream Deck application).

## Initial Handshake

Sibelius expects the first message to contain connection details, but if not it immediately closes the connection. The connection message must contain the file name without extension of every plug-in, if any, that you intend to invoke remotely.

The first message from the remote control application must be the `"connect"` message.

Here is some sample code.

```javascript
const sibsocket = new WebSocket('ws://127.0.0.1:1898');
sibsocket.onopen = function(event) {
    var connectMsg = {
        "message": "connect",
        "clientName": "NameOfYourApplication",
        "handshakeVersion": "1.0",
        "plugins": [ "plugin1", "plugin2", "plugin3" ], // optional
        // or
        "sessionToken": "{token-from-previous-connection}" // optional
    };
    sibsocket.send(JSON.stringify(connectMsg));
}
sibsocket.onmessage = function(event){
    var jsonObj = JSON.parse(event.data);
    console.log(jsonObj);
}
```

In response to the connection message, Sibelius responds:

```json
{ "sessionToken" : "SESSION_TOKEN" }
```

The `sessionToken` can be provided to re-establish a connection. In that case, the user won't be prompted. It is valid as long as Sibelius runs. Note that the plug-in list cannot be changed when re-connecting with a token.

## Commands

Sibelius commands are invoked using the `"invokeCommands"`, which expects to receive a JSON array of command IDs, like so:

```json
{ "message" : "invokeCommands", "commands": [ "command_id_1", "command_id_2", "command_id_3", ... ] }
```

For example:

```json
{"message" : "invokeCommands", "commands" : [ "select_all", "delete" ]}
```

At this time, the `invokeCommands` message always returns "success" to the caller.

Calling `"invokeCommands"` causes Sibelius to respond with a message like so:

```json
{"message":"invokeCommandsResponse","result":true}
```

## ManuScript Plug-ins

To call into a ManuScript plug-in, the `"invokePlugin"` message is used. It has a mandatory `"name"` argument that contains the file name without extension of the plug-in to call. The other two arguments (`method` and `arguments`) are optional.

It can take one of the following forms:

- Call `pluginX.Run()` (default)

  ```json
  { "message" : "invokePlugin", "name": "pluginX" }
  ```

- Call `pluginX.Method()` without arguments:

  ```json
  { "message" : "invokePlugin", "name": "pluginX", "method": "Method" }
  ```

- Call `pluginX.Method()` with the arguments provided

  ```json
  { "message" : "invokePlugin", "name": "pluginX", "method": "Method", "args": [ true, 42, 3.14159, "hello" ] }
  ```

- Call `pluginX.Method()` with the arguments provided—2nd argument is a Dictionary:

  ```json
  {"message":"invokePlugin", "name" : "testme", "method": "Method1", "args": [ 42, { "key1" : 1, "key2" : "key2 is a string"} ]}
  ```

- Call `pluginX.Method()` with the arguments provided—2nd argument is a nested Array:

  ```json
  {"message":"invokePlugin", "name" : "testme", "method": "Method1", "args": [ 42, ["v1", "v2", 37] ]}
  ```

Note that `"args"` is an array of arguments passed to the method. Each argument can be a string, boolean value, a number, an array or a dictionary. Arrays and dictionaries are represented as an embedded JSON array and object, respectively.

Also note that even though the JSON array is mapped to a ManuScript sparse array, the array is not really "sparse". Indices start at 0 and are consecutive.

- Calling `"invokePlugin"` causes Sibelius to respond with a message like:

  ```json
  {"message":"invokePluginResponse","result":true,"return_value":""}
  ```

Result indicates whether the plug-in and method were successfully found and called. When the call is successful, `"returnValue"` is the value returned by plug-in's method, if any. If the method doesn't return a value, it contains an empty string. As for arguments, strings, booleans, numbers, arrays and dictionaries are supported, with the latter 2 represented as a JSON array and object.

If the method returns an object that cannot be translated to JSON, the response message contains a JSON `null` value.
